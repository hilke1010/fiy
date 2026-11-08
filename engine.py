"""Likitgaz merkezli akaryakıt fiyat analiz motoru.

Temel kural: Her satır fiyatın GEÇERLİ OLMAYA BAŞLADIĞI tarihi temsil eder.
Takip eden kayıt gelene kadar son bilinen fiyatın geçerli olduğu varsayılır.
Ortalama fiyatı rekabet kıyaslamasında kullanmayız.
"""
from __future__ import annotations

import io
import re
import unicodedata
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

PRIMARY = 'LİKİTGAZ DAĞITIM VE ENDÜSTRİ ANONİM ŞİRKETİ'
PRIORITIES = [
    'LİKİTGAZ DAĞITIM VE ENDÜSTRİ ANONİM ŞİRKETİ',
    'AYTEMİZ AKARYAKIT DAĞITIM ANONİM ŞİRKETİ',
    'PETROL OFİSİ ANONİM ŞİRKETİ',
    'SHELL & TURCAS PETROL ANONİM ŞİRKETİ',
    'TP PETROL DAĞITIM ANONİM ŞİRKETİ',
    'AYGAZ ANONİM ŞİRKETİ',
    'BP PETROLLERİ ANONİM ŞİRKETİ',
    'GÜZEL ENERJİ AKARYAKIT ANONİM ŞİRKETİ',
    'İPRAGAZ ANONİM ŞİRKETİ',
]
BRAND_PREFIXES = [
    ('likitgaz', PRIORITIES[0]),
    ('aytemiz', PRIORITIES[1]),
    ('petrol ofisi', PRIORITIES[2]),
    ('shell turcas', PRIORITIES[3]),
    ('tp petrol', PRIORITIES[4]),
    ('aygaz', PRIORITIES[5]),
    ('bp petrolleri', PRIORITIES[6]),
    ('guzel enerji', PRIORITIES[7]),
    ('ipragaz', PRIORITIES[8]),
]
ALIAS = {
    'il': ['il adı', 'il adi', 'il', 'şehir', 'sehir'],
    'firma': ['firma adı', 'firma adi', 'firma', 'şirket', 'sirket'],
    'yakit': ['yakıt tipi', 'yakit tipi', 'yakıt', 'yakit', 'ürün', 'urun'],
    'fiyat': ['fiyat', 'pompa fiyatı', 'price'],
    'tarih': ['geçerlilik tarihi', 'gecerlilik tarihi', 'tarih', 'date'],
}

def norm(value) -> str:
    """Türkçe/Unicode, noktalama ve çoklu boşluklardan bağımsız eşleme."""
    s = unicodedata.normalize('NFKC', str(value)).strip().casefold().replace('ı', 'i')
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return ' '.join(s.split())


def canonical_company(name) -> str:
    n = norm(name)
    for prefix, target in BRAND_PREFIXES:
        if n == prefix or n.startswith(prefix + ' '):
            return target
    return ' '.join(str(name).strip().split())


def map_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Tekrar rename edilmiş sütunlar da desteklenir.
    renamed = {}
    for target, possible in ALIAS.items():
        allowed = {norm(x) for x in possible + [target]}
        matches = [col for col in df.columns if norm(col) in allowed]
        if matches:
            renamed[matches[0]] = target
    return df.rename(columns=renamed)


def parse_price(value):
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, float, np.number)):
        return float(value)
    s = str(value).strip().replace('\u00a0','').replace(' ', '')
    s = re.sub(r'(?i)(tl|try|₺)', '', s)
    s = re.sub(r'[^\d.,-]', '', s)
    if not s:
        return np.nan
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except (TypeError, ValueError):
        return np.nan


def parse_dates(series: pd.Series) -> pd.Series:
    # Excel'de tarih hücresi bazen seri numarası (ör. 45658) olarak gelir.
    as_text = series.astype('string').str.strip()
    numeric = pd.to_numeric(as_text, errors='coerce')
    numeric_mask = numeric.between(20000, 90000).fillna(False)  # Excel tarih seri sayısı
    result = pd.to_datetime(series.where(~numeric_mask), dayfirst=True, errors='coerce', format='mixed')
    if numeric_mask.any():
        result.loc[numeric_mask] = pd.to_datetime(numeric.loc[numeric_mask], unit='D', origin='1899-12-30', errors='coerce')
    return pd.to_datetime(result).dt.normalize()


def ingest(file_bytes: bytes, filename: str):
    ext = Path(filename).suffix.lower()
    stream = io.BytesIO(file_bytes)
    if ext in ('.xlsx', '.xls'):
        raw = pd.read_excel(stream, sheet_name=0)
    elif ext == '.csv':
        try:
            raw = pd.read_csv(stream, sep=None, engine='python', encoding='utf-8-sig')
        except (UnicodeDecodeError, pd.errors.ParserError):
            stream.seek(0)
            raw = pd.read_csv(stream, sep=None, engine='python', encoding='cp1254')
    else:
        raise ValueError('Lütfen .xlsx, .xls veya .csv dosyası yükleyin.')
    raw_columns = [str(x) for x in raw.columns]
    raw = map_columns(raw)
    required = ['il','firma','yakit','fiyat','tarih']
    missing = [x for x in required if x not in raw.columns]
    if missing:
        raise ValueError(f'Zorunlu sütunlar eşleşmedi: {missing}. Okunan sütunlar: {raw_columns}')

    data = raw[required].copy()
    data['__sira'] = np.arange(len(data))
    data['il'] = data['il'].astype('string').str.strip().str.upper()
    data['yakit'] = data['yakit'].astype('string').str.strip().str.title()
    data['firma'] = data['firma'].astype('string').str.strip()
    data['fiyat'] = data['fiyat'].map(parse_price)
    data['tarih'] = parse_dates(data['tarih'])
    for col in ['il','firma','yakit']:
        data.loc[data[col].eq(''), col] = pd.NA
    invalid = (data[required].isna().any(axis=1) | data['fiyat'].le(0))
    removed = int(invalid.sum())
    data = data.loc[~invalid].copy()
    data['firma'] = data['firma'].map(canonical_company)
    data['firma_key'] = data['firma'].map(norm)
    duplicates = int(data.duplicated(['il','yakit','firma_key','tarih','fiyat']).sum())
    conflicts = (data.groupby(['il','yakit','firma_key','tarih'])['fiyat'].nunique() > 1)
    conflict_count = int(conflicts.sum())
    # Aynı il/firma/ürün/tarih birden fazla fiyat ise son satır alınır, uyarı gösterilir.
    data = data.sort_values(['il','yakit','firma_key','tarih','__sira']).drop_duplicates(
        ['il','yakit','firma_key','tarih'], keep='last')
    data = data.drop(columns='__sira').reset_index(drop=True)
    data['oncelikli'] = data['firma'].isin(PRIORITIES)
    return data, {
        'ham_satir': len(raw), 'gecersiz': removed, 'tam_mukerrer': duplicates,
        'catisan_gun': conflict_count, 'kullanilan': len(data), 'ham_sutun': raw_columns,
        'ilk_tarih': data['tarih'].min() if len(data) else pd.NaT,
        'son_tarih': data['tarih'].max() if len(data) else pd.NaT,
    }


def focus_data(data, city: str, fuel: str):
    return data.loc[(data['il'] == city) & (data['yakit'] == fuel)].copy()


def events(focus: pd.DataFrame, include_initial=True) -> pd.DataFrame:
    d = focus[['il','yakit','firma','firma_key','tarih','fiyat']].sort_values(['firma_key','tarih']).copy()
    if d.empty:
        return d.assign(onceki_fiyat=pd.Series(dtype=float), fark_tl=pd.Series(dtype=float),
                        fark_yuzde=pd.Series(dtype=float), gercek_degisim=pd.Series(dtype=bool))
    d['onceki_fiyat'] = d.groupby('firma_key')['fiyat'].shift()
    d['fark_tl'] = d['fiyat'] - d['onceki_fiyat']
    d['fark_yuzde'] = (d['fark_tl'] / d['onceki_fiyat'].replace(0,np.nan)) * 100
    d['gercek_degisim'] = d['onceki_fiyat'].notna() & d['fark_tl'].abs().gt(1e-8)
    if not include_initial:
        return d.loc[d['gercek_degisim']].copy()
    return d


def price_snapshot(focus: pd.DataFrame, as_of) -> pd.DataFrame:
    """Tarihte etkin son kayıt: yalnız geçmiş fiyat kullanılır, ileri fiyat sızmaz."""
    as_of = pd.Timestamp(as_of).normalize()
    past = focus.loc[focus['tarih'] <= as_of].copy()
    cols = ['firma','firma_key','fiyat','tarih','oncelikli','kayit_yasi_gun',
            'son_degisim_tarihi','onceki_fiyat','son_degisim_tl','son_degisim_yuzde',
            'likitgaz_fiyati','likitgaz_fark_tl','likitgaz_fark_yuzde']
    if past.empty:
        return pd.DataFrame(columns=cols)
    latest = past.sort_values(['firma_key','tarih']).drop_duplicates('firma_key',keep='last').copy()
    latest['kayit_yasi_gun'] = (as_of-latest['tarih']).dt.days
    ev = events(past, include_initial=False).sort_values('tarih').drop_duplicates('firma_key',keep='last')
    latest = latest.merge(ev[['firma_key','tarih','onceki_fiyat','fark_tl','fark_yuzde']].rename(columns={
        'tarih':'son_degisim_tarihi','fark_tl':'son_degisim_tl',
        'fark_yuzde':'son_degisim_yuzde'}), on='firma_key',how='left')
    pri = latest.loc[latest['firma'] == PRIMARY,'fiyat']
    ref = float(pri.iloc[0]) if len(pri) else np.nan
    latest['likitgaz_fiyati'] = ref
    latest['likitgaz_fark_tl'] = ref - latest['fiyat']
    latest['likitgaz_fark_yuzde'] = np.where(pd.notna(ref) and ref != 0,
                                              latest['likitgaz_fark_tl']/latest['fiyat'].replace(0,np.nan)*100, np.nan)
    latest['__rank'] = latest['firma'].map({v:i for i,v in enumerate(PRIORITIES)}).fillna(99)
    latest = latest.sort_values(['__rank','firma']).drop(columns='__rank')
    return latest[cols].reset_index(drop=True)


def price_timeline(focus: pd.DataFrame, start, end, companies=None) -> pd.DataFrame:
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if start > end:
        return pd.DataFrame(columns=['tarih','firma','fiyat','likitgaz_fiyati','likitgaz_fark_tl','likitgaz_fark_yuzde'])
    d = focus.loc[focus['tarih'] <= end, ['tarih','firma','fiyat']].copy()
    if companies is not None:
        d = d[d['firma'].isin(set(companies) | {PRIMARY})]
    if d.empty:
        return pd.DataFrame(columns=['tarih','firma','fiyat','likitgaz_fiyati','likitgaz_fark_tl','likitgaz_fark_yuzde'])
    # Tarih noktaları: aralığın ilk/son günü ve gerçek kayıt değişim günleri.
    days = pd.DatetimeIndex(sorted(set(d.loc[d['tarih'].between(start,end),'tarih'].tolist() + [start,end])))
    matrix = d.pivot_table(index='tarih', columns='firma', values='fiyat', aggfunc='last')
    matrix = matrix.reindex(matrix.index.union(days)).sort_index().ffill().reindex(days)
    if PRIMARY not in matrix.columns:
        matrix[PRIMARY] = np.nan
    long = matrix.stack(future_stack=True).rename('fiyat').reset_index()
    long.columns = ['tarih','firma','fiyat']
    ref = matrix[PRIMARY].rename('likitgaz_fiyati')
    long = long.merge(ref, left_on='tarih',right_index=True,how='left')
    long['likitgaz_fark_tl'] = long['likitgaz_fiyati'] - long['fiyat']
    long['likitgaz_fark_yuzde'] = long['likitgaz_fark_tl'] / long['fiyat'].replace(0,np.nan)*100
    return long.sort_values(['tarih','firma']).reset_index(drop=True)


def monthly_history(focus: pd.DataFrame, start, end) -> pd.DataFrame:
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if end < start:
        return pd.DataFrame()
    records = []
    for month in pd.period_range(start, end, freq='M'):
        effective_date = min(month.end_time.normalize(), end.normalize())
        snap = price_snapshot(focus, effective_date)
        if snap.empty:
            continue
        part = snap[['firma','fiyat','tarih','likitgaz_fark_tl','likitgaz_fark_yuzde','kayit_yasi_gun']].copy()
        part['ay'] = str(month)
        part['ay_sonu'] = effective_date
        records.append(part)
    if not records:
        return pd.DataFrame()
    d = pd.concat(records,ignore_index=True).sort_values(['firma','ay_sonu'])
    d['onceki_ay_fiyati'] = d.groupby('firma')['fiyat'].shift(1)
    d['aylik_degisim_tl'] = d['fiyat'] - d['onceki_ay_fiyati']
    d['aylik_degisim_yuzde'] = d['aylik_degisim_tl']/d['onceki_ay_fiyati'].replace(0,np.nan)*100
    d['onceki_ay_degisim_yuzde'] = d.groupby('firma')['aylik_degisim_yuzde'].shift(1)
    d['degisim_hizi_farki_puan'] = d['aylik_degisim_yuzde'] - d['onceki_ay_degisim_yuzde']
    likit_month = d[d['firma']==PRIMARY][['ay','aylik_degisim_tl','aylik_degisim_yuzde']].rename(columns={
        'aylik_degisim_tl':'likitgaz_aylik_degisim_tl',
        'aylik_degisim_yuzde':'likitgaz_aylik_degisim_yuzde'})
    d = d.merge(likit_month,on='ay',how='left')
    d['likitgaz_aylik_degisim_farki_tl'] = d['aylik_degisim_tl'] - d['likitgaz_aylik_degisim_tl']
    d['likitgaz_aylik_degisim_farki_puan'] = d['aylik_degisim_yuzde'] - d['likitgaz_aylik_degisim_yuzde']
    return d[['ay','ay_sonu','firma','fiyat','onceki_ay_fiyati','aylik_degisim_tl',
              'aylik_degisim_yuzde','onceki_ay_degisim_yuzde','degisim_hizi_farki_puan',
              'likitgaz_aylik_degisim_tl','likitgaz_aylik_degisim_yuzde',
              'likitgaz_aylik_degisim_farki_tl','likitgaz_aylik_degisim_farki_puan',
              'likitgaz_fark_tl','likitgaz_fark_yuzde',
              'tarih','kayit_yasi_gun']].sort_values(['ay_sonu','firma']).reset_index(drop=True)


def two_date_compare(focus: pd.DataFrame, first, second):
    a, b = price_snapshot(focus,first), price_snapshot(focus,second)
    a = a[['firma','fiyat','tarih','likitgaz_fark_tl']].rename(columns={
        'fiyat':'fiyat_ilk','tarih':'son_kayit_ilk','likitgaz_fark_tl':'likitgaz_fark_ilk'})
    b = b[['firma','fiyat','tarih','likitgaz_fark_tl']].rename(columns={
        'fiyat':'fiyat_son','tarih':'son_kayit_son','likitgaz_fark_tl':'likitgaz_fark_son'})
    merged = a.merge(b,on='firma',how='outer')
    merged['degisim_tl'] = merged['fiyat_son'] - merged['fiyat_ilk']
    merged['degisim_yuzde'] = merged['degisim_tl']/merged['fiyat_ilk'].replace(0,np.nan)*100
    merged['rekabet_farki_degisim_tl'] = merged['likitgaz_fark_son'] - merged['likitgaz_fark_ilk']
    merged['__rank'] = merged['firma'].map({v:i for i,v in enumerate(PRIORITIES)}).fillna(99)
    return merged.sort_values(['__rank','firma']).drop(columns='__rank').reset_index(drop=True)


def event_comparisons(focus: pd.DataFrame, start, end) -> pd.DataFrame:
    ev = events(focus, include_initial=False)
    ev = ev.loc[ev['tarih'].between(pd.Timestamp(start),pd.Timestamp(end))].copy()
    if ev.empty:
        return ev
    # O günkü LIKITGAZ fiyatı: tarih <= olay tarihi (as-of), veri olmayan günlerde NaN.
    primary = focus.loc[focus['firma'] == PRIMARY,['tarih','fiyat']].sort_values('tarih').rename(columns={
        'tarih':'likitgaz_son_tarihi','fiyat':'likitgaz_fiyati'})
    ev = ev.sort_values('tarih')
    if len(primary):
        ev = pd.merge_asof(ev, primary, left_on='tarih', right_on='likitgaz_son_tarihi', direction='backward')
    else:
        ev['likitgaz_son_tarihi'] = pd.NaT
        ev['likitgaz_fiyati'] = np.nan
    ev['likitgaz_fark_tl'] = ev['likitgaz_fiyati'] - ev['fiyat']
    ev['likitgaz_fark_yuzde'] = ev['likitgaz_fark_tl']/ev['fiyat'].replace(0,np.nan)*100
    return ev.sort_values(['tarih','firma'],ascending=[False,True]).reset_index(drop=True)


def day_advantage(timeline: pd.DataFrame, end) -> pd.DataFrame:
    if timeline.empty:
        return pd.DataFrame()
    x = timeline.loc[timeline['firma'] != PRIMARY].copy()
    x['sonraki_tarih'] = x.groupby('firma')['tarih'].shift(-1).fillna(pd.Timestamp(end)+pd.Timedelta(days=1))
    x['gun'] = (x['sonraki_tarih'] - x['tarih']).dt.days.clip(lower=0)
    x = x.loc[x['fiyat'].notna() & x['likitgaz_fiyati'].notna()].copy()
    if x.empty:
        return pd.DataFrame()
    x['likitgaz_ucuz_gun'] = np.where(x['likitgaz_fark_tl']>1e-8,x['gun'],0)
    x['likitgaz_pahali_gun'] = np.where(x['likitgaz_fark_tl']<-1e-8,x['gun'],0)
    x['esit_gun'] = np.where(x['likitgaz_fark_tl'].abs()<=1e-8,x['gun'],0)
    out = x.groupby('firma',as_index=False).agg(
        karsilastirilabilir_gun=('gun','sum'),
        likitgaz_ucuz_gun=('likitgaz_ucuz_gun','sum'),
        likitgaz_pahali_gun=('likitgaz_pahali_gun','sum'),
        esit_gun=('esit_gun','sum'),
    )
    out['likitgaz_ucuz_oran_yuzde'] = out['likitgaz_ucuz_gun']/out['karsilastirilabilir_gun'].replace(0,np.nan)*100
    return out.sort_values('likitgaz_ucuz_gun',ascending=False)


def recent_change_metrics(focus: pd.DataFrame, as_of):
    evt = events(focus.loc[focus['tarih'] <= pd.Timestamp(as_of)], include_initial=False)
    if evt.empty:
        return {'toplam_degisim':0,'likitgaz_degisim':0,'son_30_gun':0}
    cutoff = pd.Timestamp(as_of) - pd.Timedelta(days=30)
    return {'toplam_degisim':len(evt),'likitgaz_degisim':int((evt['firma'] == PRIMARY).sum()),
            'son_30_gun':int((evt['tarih'] > cutoff).sum())}


def nationwide_snapshot(data: pd.DataFrame, as_of, companies=None) -> pd.DataFrame:
    """Tüm il/ürünlerde aynı tarihte etkin olan son fiyat; vektörize analiz."""
    as_of = pd.Timestamp(as_of)
    past = data.loc[data['tarih'] <= as_of].copy()
    if companies is not None:
        past = past[past['firma'].isin(set(companies) | {PRIMARY})]
    if past.empty:
        return pd.DataFrame()
    latest = (past.sort_values('tarih').drop_duplicates(['il','yakit','firma_key'],keep='last')
              [['il','yakit','firma','fiyat','tarih']].copy())
    ref = latest.loc[latest['firma'] == PRIMARY,['il','yakit','fiyat','tarih']].rename(columns={
        'fiyat':'likitgaz_fiyati','tarih':'likitgaz_son_kayit'})
    latest = latest.merge(ref,on=['il','yakit'],how='left')
    latest['fark_tl'] = latest['likitgaz_fiyati'] - latest['fiyat']
    latest['fark_yuzde'] = latest['fark_tl']/latest['fiyat'].replace(0,np.nan)*100
    latest['kayit_yasi_gun'] = (as_of-latest['tarih']).dt.days
    latest['likitgaz_kayit_yasi_gun'] = (as_of-latest['likitgaz_son_kayit']).dt.days
    latest = latest.sort_values(['il','yakit','firma'])
    return latest.reset_index(drop=True)


def asof_matrix(data: pd.DataFrame, fuel: str, as_of, companies, cities=None, mode='fark_tl'):
    """İl x rakip matrisi. Negatif fark: Likitgaz fiyatı rakibin altında, pozitif: üzerinde."""
    subset = data[data['yakit'].eq(fuel)]
    if cities:
        subset = subset[subset['il'].isin(cities)]
    companies = list(dict.fromkeys([PRIMARY] + [x for x in companies if x != PRIMARY]))
    snap = nationwide_snapshot(subset, as_of, companies)
    if snap.empty:
        return pd.DataFrame(columns=['İl', 'LİKİTGAZ (TL)'])
    pivot = snap.pivot(index='il',columns='firma',values='fiyat')
    ref = pivot[PRIMARY] if PRIMARY in pivot else pd.Series(np.nan,index=pivot.index)
    matrix = pd.DataFrame({'İl':pivot.index, 'LİKİTGAZ (TL)':ref.values},index=pivot.index)
    for competitor in companies[1:]:
        rival = pivot[competitor] if competitor in pivot else pd.Series(np.nan,index=pivot.index)
        if mode == 'fiyat':
            value = rival
        elif mode == 'fark_yuzde':
            value = (ref - rival) / rival.replace(0, np.nan)*100
        else:
            value = ref - rival
        matrix[competitor] = value
    return matrix.reset_index(drop=True)


def machine_analysis(data: pd.DataFrame, fuel: str, companies, cities, as_of,
                     threshold_tl=1.0, threshold_pp=2.0):
    """Üç karşılaştırma anındaki geçerli fiyatların tarafsız, ayrıntılı analizi.

    Önceki/son fiyat değişimleri yalnız gerçek değişim kaydı içeriyorsa belirtilir.
    Karşılaştırma tarihleri zam tarihi olarak sunulmaz.
    """
    when = pd.Timestamp(as_of).normalize()
    previous = when.replace(day=1) - pd.Timedelta(days=1)
    older = previous.replace(day=1) - pd.Timedelta(days=1)
    dates = {'simdi':when, 'onceki':previous, 'eski':older}
    subset = data[data['yakit'].eq(fuel)]
    if cities:
        subset = subset[subset['il'].isin(cities)]
    rivals = list(dict.fromkeys(x for x in companies if x != PRIMARY))
    subset = subset[subset['firma'].isin([PRIMARY]+rivals)].copy()
    keys = ['il','yakit','firma']

    def prices_at(day, prefix):
        p = subset.loc[subset['tarih'].le(day)]
        if p.empty:
            return pd.DataFrame(columns=keys+[f'{prefix}_fiyat',f'{prefix}_tarih'])
        p = p.sort_values('tarih').drop_duplicates(keys,keep='last')
        return p[keys+['fiyat','tarih']].rename(columns={
            'fiyat':f'{prefix}_fiyat','tarih':f'{prefix}_tarih'})

    now = prices_at(when,'simdi')
    prev = prices_at(previous,'onceki')
    old = prices_at(older,'eski')
    if now.empty:
        return pd.DataFrame(),pd.DataFrame(),dates
    joined = now.merge(prev,on=keys,how='left').merge(old,on=keys,how='left')
    li = joined[joined['firma'].eq(PRIMARY)].drop(columns='firma').copy()
    li = li.rename(columns={x:'li_'+x for x in [
        'simdi_fiyat','onceki_fiyat','eski_fiyat','simdi_tarih','onceki_tarih','eski_tarih']})
    rival = joined[joined['firma'].ne(PRIMARY)].merge(li,on=['il','yakit'],how='left')
    rival['fark_simdi'] = rival['li_simdi_fiyat'] - rival['simdi_fiyat']
    rival['fark_onceki'] = rival['li_onceki_fiyat'] - rival['onceki_fiyat']
    rival['fark_degisimi'] = rival['fark_simdi'] - rival['fark_onceki']
    rival['rakip_son_degis_pct'] = (rival['simdi_fiyat']/rival['onceki_fiyat'].replace(0,np.nan)-1)*100
    rival['rakip_onceki_degis_pct'] = (rival['onceki_fiyat']/rival['eski_fiyat'].replace(0,np.nan)-1)*100
    rival['rakip_zam_hizi_fark_pp'] = rival['rakip_son_degis_pct']-rival['rakip_onceki_degis_pct']
    rival['li_son_degis_pct'] = (rival['li_simdi_fiyat']/rival['li_onceki_fiyat'].replace(0,np.nan)-1)*100
    rival['zam_yuzde_fark_pp'] = rival['rakip_son_degis_pct']-rival['li_son_degis_pct']
    rival['rakip_kayit_yasi'] = (when-rival['simdi_tarih']).dt.days
    rival['li_kayit_yasi'] = (when-rival['li_simdi_tarih']).dt.days
    rival = rival.sort_values(['il','firma']).reset_index(drop=True)

    # Gerçek fiyat değişimleri; yalnız ilk kayıt veya aynı fiyattaki mükerrer
    # tarih kesinlikle 'zam' ya da 'indirim' olarak gösterilmez.
    event_history = events(subset[subset['tarih'].le(when)],include_initial=False)
    histories = {(il,firm): group.sort_values('tarih')
                 for (il,firm),group in event_history.groupby(['il','firma'])}

    def tr(v,sign=False):
        if pd.isna(v): return '—'
        return f'{float(v):+,.2f}'.replace(',','Q').replace('.',',').replace('Q','.') if sign else f'{float(v):,.2f}'.replace(',','Q').replace('.',',').replace('Q','.')

    def tr_date(v):
        return pd.Timestamp(v).strftime('%d.%m.%Y') if pd.notna(v) else 'kayıt yok'

    def relation(diff,company):
        if pd.isna(diff):return 'karşılaştırma için yeterli fiyat kaydı bulunmamaktadır'
        if diff < -1e-8:return f'Likitgaz fiyatı {company} fiyatından {tr(abs(diff))} TL düşüktür'
        if diff > 1e-8:return f'Likitgaz fiyatı {company} fiyatından {tr(abs(diff))} TL yüksektir'
        return f'Likitgaz fiyatı ile {company} fiyatı eşittir'

    def movement(v0,v1):
        if pd.isna(v0) or pd.isna(v1):return 'karşılaştırma için yeterli fiyat kaydı yoktur'
        diff = float(v1-v0)
        if abs(diff)<1e-8:return 'fiyat değişmedi (0,00 TL)'
        kind = 'arttı' if diff>0 else 'azaldı'
        pc = (diff/v0*100) if v0 != 0 else np.nan
        return f'fiyat {tr(abs(diff))} TL {kind} ({tr(diff,True)} TL; %{tr(pc,True)})'

    def actual_changes(city,company):
        hist = histories.get((city,company))
        if hist is None or hist.empty:
            return 'Kaynakta ilk fiyat kaydı dışında doğrulanabilen fiyat değişimi bulunmuyor.'
        within = hist[hist['tarih'].gt(previous) & hist['tarih'].le(when)]
        if within.empty:
            last=hist.iloc[-1]
            return (f'İki karşılaştırma tarihi arasında yeni fiyat hareketi kayıtlı değil. '
                    f'Kaynakta tespit edilen son gerçek fiyat değişimi {tr_date(last.tarih)} '
                    f'tarihinde {tr(last.onceki_fiyat)} TL → {tr(last.fiyat)} TL '
                    f'({tr(last.fark_tl,True)} TL) şeklindedir.')
        movements=[]
        for x in within.tail(4).itertuples(index=False):
            kind='zam' if x.fark_tl>0 else 'indirim'
            movements.append(f'{tr_date(x.tarih)}: {tr(x.onceki_fiyat)} TL → {tr(x.fiyat)} TL '
                             f'({kind}, {tr(x.fark_tl,True)} TL; %{tr(x.fark_yuzde,True)})')
        lead=f'Bu iki tarih arasında {len(within)} ayrı fiyat değişimi kayıtlıdır. '
        if len(within)>4:lead+='Son dört hareket: '
        return lead + '; '.join(movements) + '.'

    findings=[]
    for r in rival.itertuples(index=False):
        base={'İl':r.il,'Ürün':r.yakit,'Rakip':r.firma,
              'Önceki Fark (TL)':r.fark_onceki,'Yeni Fark (TL)':r.fark_simdi,
              'Fark Değişimi (TL)':r.fark_degisimi,
              'Son Dönem Rakip (%)':r.rakip_son_degis_pct,
              'Önceki Dönem Rakip (%)':r.rakip_onceki_degis_pct,
              'Son Dönem Likitgaz (%)':r.li_son_degis_pct}
        def make_detail(overview):
            parts=[f'**📌 Tespit:** {overview}',
                f'**📅 Karşılaştırılan dönem sonları:** Önceki dönem **{tr_date(previous)}**, son dönem **{tr_date(when)}**. '
                'Bunlar fiyatların karşılaştırıldığı günlerdir; her iki şirketin o gün fiyat değiştirdiği anlamına gelmez.',
                (f'**📍 {tr_date(previous)} tarihinde geçerli fiyatlar:** '
                 f'Likitgaz **{tr(r.li_onceki_fiyat)} TL** (son fiyat kaydı: {tr_date(r.li_onceki_tarih)}); '
                 f'{r.firma} **{tr(r.onceki_fiyat)} TL** (son fiyat kaydı: {tr_date(r.onceki_tarih)}). '
                 f'{relation(r.fark_onceki,r.firma)}.'),
                (f'**📍 {tr_date(when)} tarihinde geçerli fiyatlar:** '
                 f'Likitgaz **{tr(r.li_simdi_fiyat)} TL** (son fiyat kaydı: {tr_date(r.li_simdi_tarih)}); '
                 f'{r.firma} **{tr(r.simdi_fiyat)} TL** (son fiyat kaydı: {tr_date(r.simdi_tarih)}). '
                 f'{relation(r.fark_simdi,r.firma)}.'),
                (f'**🧮 Fiyat farkı nasıl hesaplanır?** **Likitgaz fiyatı − rakip fiyatı**. '
                 f'Önceki dönemde {tr(r.li_onceki_fiyat)} − {tr(r.onceki_fiyat)} = '
                 f'**{tr(r.fark_onceki,True)} TL**; son dönemde {tr(r.li_simdi_fiyat)} − '
                 f'{tr(r.simdi_fiyat)} = **{tr(r.fark_simdi,True)} TL**. '
                 f'Farkın dönemsel değişimi **{tr(r.fark_degisimi,True)} TL** '\
                 f'(yeni fark − önceki fark). Negatif sonuç Likitgaz fiyatının daha düşük, '
                 f'pozitif sonuç daha yüksek olduğunu belirtir. İşaret, iyi veya kötü değerlendirmesi değildir.'),
                (f'**📏 Farkın büyüklüğü:** Önceki dönemde **{tr(abs(r.fark_onceki))} TL**, '
                 f'son dönemde **{tr(abs(r.fark_simdi))} TL**. '
                 f'Mutlak farkın değişimi **{tr(abs(r.fark_simdi)-abs(r.fark_onceki),True)} TL**. '
                 'Mutlak fark, fiyatların birbirine olan uzaklığıdır ve işaret içermez.'),
                (f'**📈 Dönemde iki şirketin fiyat hareketi:** Likitgaz {tr(r.li_onceki_fiyat)} TL → '
                 f'{tr(r.li_simdi_fiyat)} TL; {movement(r.li_onceki_fiyat,r.li_simdi_fiyat)}. '
                 f'{r.firma} {tr(r.onceki_fiyat)} TL → {tr(r.simdi_fiyat)} TL; '
                 f'{movement(r.onceki_fiyat,r.simdi_fiyat)}.'),
                (f'**🗓️ Kaynaktaki gerçek fiyat değişim tarihleri — Likitgaz:** '
                 f'{actual_changes(r.il,PRIMARY)}'),
                (f'**🗓️ Kaynaktaki gerçek fiyat değişim tarihleri — {r.firma}:** '
                 f'{actual_changes(r.il,r.firma)}'),
            ]
            return '\n\n'.join(parts)
        def push(priority,icon,signal,overview,score):
            findings.append({**base,'Öncelik':priority,'Simge':icon,'Sinyal':signal,
                             'Bulgular':make_detail(overview),'Etki Puanı':score})

        if pd.notna(r.fark_simdi) and pd.notna(r.fark_onceki):
            old_abs,now_abs=abs(r.fark_onceki),abs(r.fark_simdi)
            if r.fark_onceki*r.fark_simdi < -1e-12:
                push(0,'🔀','Fiyat sıralaması değişti',
                     f'{r.il} / {r.yakit}: Önceki tarihte {relation(r.fark_onceki,r.firma)}; '
                     f'son tarihte {relation(r.fark_simdi,r.firma)}. '
                     f'Fiyat farkı {tr(r.fark_onceki,True)} TL → {tr(r.fark_simdi,True)} TL. '
                     'Fiyat farkının eksi/arti işareti değişmiştir.',
                     100+abs(r.fark_degisimi))
            elif ((abs(r.fark_onceki)<1e-8) != (abs(r.fark_simdi)<1e-8)):
                push(0,'↔️','Fiyat eşitliği değişti',
                     f'{r.il} / {r.yakit}: Önceki fark {tr(r.fark_onceki,True)} TL, '
                     f'son fark {tr(r.fark_simdi,True)} TL. '
                     f'Önceki durum: {relation(r.fark_onceki,r.firma)}; '
                     f'son durum: {relation(r.fark_simdi,r.firma)}.',
                     100+abs(r.fark_degisimi))
            abs_delta=now_abs-old_abs
            if abs(abs_delta)>=threshold_tl:
                title='Fiyat farkının büyüklüğü arttı' if abs_delta>0 else 'Fiyat farkının büyüklüğü azaldı'
                push(1,'📐' if abs_delta>0 else '↘️',title,
                     f'{r.il} / {r.yakit}: {r.firma} ile iki fiyat arasındaki mutlak fark '
                     f'{tr(old_abs)} TL → {tr(now_abs)} TL ({tr(abs_delta,True)} TL). '
                     f'Likitgaz − rakip farkı {tr(r.fark_onceki,True)} TL → '
                     f'{tr(r.fark_simdi,True)} TL.',abs(abs_delta))
            elif abs(r.fark_degisimi)>=threshold_tl:
                push(2,'🔁','Fiyat farkı değişti',
                     f'{r.il} / {r.yakit}: Likitgaz − {r.firma} fiyat farkı '
                     f'{tr(r.fark_onceki,True)} TL → {tr(r.fark_simdi,True)} TL. '
                     f'İki fark arasındaki aritmetik değişim {tr(r.fark_degisimi,True)} TL.',
                     abs(r.fark_degisimi))
        if pd.notna(r.rakip_zam_hizi_fark_pp) and abs(r.rakip_zam_hizi_fark_pp)>=threshold_pp:
            title=('Rakibin dönemsel değişim oranı yükseldi' if r.rakip_zam_hizi_fark_pp>0
                   else 'Rakibin dönemsel değişim oranı düştü')
            push(3,'📈' if r.rakip_zam_hizi_fark_pp>0 else '📉',title,
                 f'{r.il} / {r.yakit}: {r.firma} fiyatının {tr_date(older)} → '
                 f'{tr_date(previous)} dönemindeki değişimi %{tr(r.rakip_onceki_degis_pct,True)}, '
                 f'{tr_date(previous)} → {tr_date(when)} dönemindeki değişimi '
                 f'%{tr(r.rakip_son_degis_pct,True)}. İki dönem arasındaki değişim oranı '
                 f'farkı {tr(r.rakip_zam_hizi_fark_pp,True)} yüzde puandır.',
                 abs(r.rakip_zam_hizi_fark_pp))
        if pd.notna(r.zam_yuzde_fark_pp) and abs(r.zam_yuzde_fark_pp)>=threshold_pp:
            push(4,'⚡','Dönemsel değişim oranları farklılaştı',
                 f'{r.il} / {r.yakit}: Son karşılaştırma döneminde {r.firma} fiyatı '
                 f'%{tr(r.rakip_son_degis_pct,True)}, Likitgaz fiyatı '
                 f'%{tr(r.li_son_degis_pct,True)} değişti. Rakip yüzdesi eksi '
                 f'Likitgaz yüzdesi = {tr(r.zam_yuzde_fark_pp,True)} yüzde puan.',
                 abs(r.zam_yuzde_fark_pp))
        if pd.notna(r.fark_simdi) and abs(r.fark_simdi)>=threshold_tl*2:
            push(5,'🔎','Güncel fiyat farkı eşik üzerinde',
                 f'{r.il} / {r.yakit}: {tr_date(when)} tarihinde '
                 f'{relation(r.fark_simdi,r.firma)}. '
                 f'Fiyat farkı {tr(r.fark_simdi,True)} TL.',abs(r.fark_simdi))
        if r.rakip_kayit_yasi>90 or (pd.notna(r.li_kayit_yasi) and r.li_kayit_yasi>90):
            li_days=int(r.li_kayit_yasi) if pd.notna(r.li_kayit_yasi) else 'kayıt yok'
            push(6,'⚠️','Eski fiyat kaydı',
                 f'{r.il} / {r.yakit}: {tr_date(when)} tarihine göre '
                 f'{r.firma} fiyat kaydı {int(r.rakip_kayit_yasi)} günlük; '
                 f'Likitgaz fiyat kaydı {li_days} günlük. Bu süreler, kaynaktaki '
                 'son kayıt tarihinden hesaplanmıştır ve gerçek piyasa güncelliğinin '
                 'ayrıca teyit edilmesi gerekir.',
                 max(float(r.rakip_kayit_yasi),float(r.li_kayit_yasi) if pd.notna(r.li_kayit_yasi) else 0))
    findings_df=pd.DataFrame(findings)
    if not findings_df.empty:
        findings_df=(findings_df.sort_values(['Öncelik','Etki Puanı','İl','Rakip'],
                      ascending=[True,False,True,True]).reset_index(drop=True))
    return findings_df,rival,dates
