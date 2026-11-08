# -*- coding: utf-8 -*-
"""V5: gerçek fiyat değişim noktaları, odak firma analizi ve il haritaları."""
from __future__ import annotations
import numpy as np
import pandas as pd
from engine import PRIMARY

EPS = 1e-8


def fmt(x, unit='', signed=False):
    if pd.isna(x): return '—'
    spec = '+,.2f' if signed else ',.2f'
    return format(float(x), spec).replace(',', 'Q').replace('.', ',').replace('Q', '.') + unit


def day_str(x):
    return pd.Timestamp(x).strftime('%d.%m.%Y') if pd.notna(x) else 'kayıt yok'


def true_changes(data: pd.DataFrame) -> pd.DataFrame:
    """İlk fiyatlar zam sayılmaz; her il/yakıt/firma ayrı izlenir."""
    if data.empty:
        return pd.DataFrame(columns=['il','yakit','firma','tarih','fiyat','onceki_fiyat','degisim_tl','degisim_yuzde'])
    cols=['il','yakit','firma','tarih','fiyat']
    q=data[cols].sort_values(['il','yakit','firma','tarih'],kind='stable').copy()
    key=['il','yakit','firma']
    q['onceki_fiyat']=q.groupby(key,dropna=False)['fiyat'].shift()
    q['degisim_tl']=q['fiyat']-q['onceki_fiyat']
    q['degisim_yuzde']=100*q['degisim_tl']/q['onceki_fiyat'].replace(0,np.nan)
    q=q[q['onceki_fiyat'].notna() & q['degisim_tl'].abs().gt(EPS)]
    return q.reset_index(drop=True)


def event_dates(data, fuel=None, companies=None, cities=None):
    t=data
    if fuel is not None:t=t[t['yakit'].eq(fuel)]
    if companies is not None:t=t[t['firma'].isin(companies)]
    if cities:t=t[t['il'].isin(cities)]
    changes=true_changes(t)
    days=sorted(pd.to_datetime(changes['tarih'].dropna().unique()).to_pydatetime().tolist())
    if not days:
        days=sorted(pd.to_datetime(t['tarih'].dropna().unique()).to_pydatetime().tolist())
    return [pd.Timestamp(x).normalize() for x in days]


def effective_snapshot(data, when, fuel=None, companies=None, cities=None):
    t=data[data['tarih'].le(pd.Timestamp(when).normalize())]
    if fuel is not None:t=t[t['yakit'].eq(fuel)]
    if companies is not None:t=t[t['firma'].isin(companies)]
    if cities:t=t[t['il'].isin(cities)]
    if t.empty:
        return pd.DataFrame(columns=['il','yakit','firma','fiyat','tarih','kayit_yasi'])
    t=t.sort_values('tarih').drop_duplicates(['il','yakit','firma'],keep='last')
    t=t[['il','yakit','firma','fiyat','tarih']].copy()
    t['kayit_yasi']=(pd.Timestamp(when).normalize()-t['tarih']).dt.days
    return t.reset_index(drop=True)


def province_comparison(data, fuel, when, firms, benchmark=PRIMARY):
    """81 il × firma, tarihi gelememiş fiyatları kullanmadan."""
    companies=list(dict.fromkeys([benchmark]+list(firms)))
    snap=effective_snapshot(data, when, fuel, companies)
    if snap.empty:return snap
    base=snap[snap['firma'].eq(benchmark)][['il','fiyat','tarih']].rename(columns={
        'fiyat':'baz_fiyat','tarih':'baz_kayit_tarihi'})
    snap=snap.merge(base,on='il',how='left')
    snap['baz_fark_tl']=snap['baz_fiyat']-snap['fiyat']
    snap['baz_fark_yuzde']=100*snap['baz_fark_tl']/snap['fiyat'].replace(0,np.nan)
    return snap


def province_winners(data,fuel,when,firms,which='max'):
    snap=effective_snapshot(data,when,fuel,firms)
    if snap.empty:return pd.DataFrame(columns=['il','firma','fiyat','tarih','bagli']),snap
    extreme=snap.groupby('il')['fiyat'].transform('max' if which=='max' else 'min')
    best=snap[np.isclose(snap['fiyat'],extreme,atol=1e-8)].copy()
    tied=best.groupby('il')['firma'].transform('size')
    best['bagli']=tied.gt(1)
    best['rakipler_esit']=best.groupby('il')['firma'].transform(lambda s:', '.join(sorted(s)))
    return best.sort_values(['il','firma']).drop_duplicates('il'),snap


def comparative_periods(data, fuel, anchor, others, cities, beginning, ending):
    """Başlangıç/bitiş gerçek zam tarihleriyle; 2 tarihli etkin fiyat karşılaştırması."""
    base=[anchor]+[f for f in others if f!=anchor]
    before=effective_snapshot(data,beginning,fuel,base,cities)
    after=effective_snapshot(data,ending,fuel,base,cities)
    keys=['il','firma']
    before=before.rename(columns={'fiyat':'ilk_fiyat','tarih':'ilk_kayit'})
    after=after.rename(columns={'fiyat':'son_fiyat','tarih':'son_kayit'})
    joined=after.merge(before[keys+['ilk_fiyat','ilk_kayit']],on=keys,how='left')
    anchor_prices=joined[joined['firma'].eq(anchor)][['il','ilk_fiyat','son_fiyat','ilk_kayit','son_kayit']]
    anchor_prices=anchor_prices.rename(columns={c:'baz_'+c for c in ['ilk_fiyat','son_fiyat','ilk_kayit','son_kayit']})
    other=joined[~joined['firma'].eq(anchor)].merge(anchor_prices,on='il',how='left')
    if other.empty:
        return other
    for when in ['ilk','son']:
        other[when+'_fark']=other['baz_'+when+'_fiyat']-other[when+'_fiyat']
    other['fark_degisimi']=other['son_fark']-other['ilk_fark']
    other['mutlak_fark_degisimi']=other['son_fark'].abs()-other['ilk_fark'].abs()
    other['baz_degisim_tl']=other['baz_son_fiyat']-other['baz_ilk_fiyat']
    other['rakip_degisim_tl']=other['son_fiyat']-other['ilk_fiyat']
    other['baz_degisim_pct']=100*other['baz_degisim_tl']/other['baz_ilk_fiyat'].replace(0,np.nan)
    other['rakip_degisim_pct']=100*other['rakip_degisim_tl']/other['ilk_fiyat'].replace(0,np.nan)
    other['yuzde_puan_farki']=other['baz_degisim_pct']-other['rakip_degisim_pct']
    return other.sort_values(['il','firma']).reset_index(drop=True)


def company_change_report(data, fuel, company, cities, beginning, ending):
    t=data[data['yakit'].eq(fuel) & data['firma'].eq(company)]
    if cities:t=t[t['il'].isin(cities)]
    changes=true_changes(t)
    return changes[changes['tarih'].between(pd.Timestamp(beginning),pd.Timestamp(ending))].sort_values(
        ['tarih','il'],ascending=[False,True]).reset_index(drop=True)


def detail_insights(data,fuel,anchor,rivals,cities,beginning,ending,threshold=0.5,max_results=350):
    """Yorum yerine doğrulanabilir, değişim tarihli, tarafsız bulgular."""
    periods=comparative_periods(data,fuel,anchor,rivals,cities,beginning,ending)
    if periods.empty:return pd.DataFrame(columns=['Simge','Başlık','İl','Rakip','Öncelik','Açıklama']),periods
    within=data[data['yakit'].eq(fuel) & data['firma'].isin([anchor]+list(rivals))]
    if cities:within=within[within['il'].isin(cities)]
    changes=true_changes(within[within['tarih'].le(pd.Timestamp(ending))])
    history={(city,firm):x.sort_values('tarih') for (city,firm),x in changes.groupby(['il','firma'])}
    results=[]
    def last_event(city,firm):
        h=history.get((city,firm))
        if h is None or h.empty:return 'İlk fiyat kaydı dışında doğrulanmış değişim yok.'
        latest=h.iloc[-1]
        return (f'{day_str(latest.tarih)} tarihinde {fmt(latest.onceki_fiyat)} TL → '
                f'{fmt(latest.fiyat)} TL; değişim {fmt(latest.degisim_tl,signed=True)} TL '
                f'(%{fmt(latest.degisim_yuzde,signed=True)}).')
    for r in periods.itertuples(index=False):
        if pd.isna(r.son_fark):continue
        old_relation='daha düşük' if r.ilk_fark < -EPS else ('daha yüksek' if r.ilk_fark > EPS else 'eşit') if pd.notna(r.ilk_fark) else 'hesaplanamadı'
        new_relation='daha düşük' if r.son_fark < -EPS else ('daha yüksek' if r.son_fark > EPS else 'eşit')
        if pd.notna(r.ilk_fark):
            explanation=(f'**{r.il} · {fuel} · {anchor} / {r.firma}**\n\n'
                f'**Başlangıç dönemi ({day_str(beginning)}):** {anchor} {fmt(r.baz_ilk_fiyat)} TL '
                f'(son fiyat kaydı {day_str(r.baz_ilk_kayit)}); {r.firma} {fmt(r.ilk_fiyat)} TL '
                f'(son fiyat kaydı {day_str(r.ilk_kayit)}). Odak dağıtıcının fiyatı rakibe göre **{old_relation}**.\n\n'
                f'**Bitiş dönemi ({day_str(ending)}):** {anchor} {fmt(r.baz_son_fiyat)} TL '
                f'(son fiyat kaydı {day_str(r.baz_son_kayit)}); {r.firma} {fmt(r.son_fiyat)} TL '
                f'(son fiyat kaydı {day_str(r.son_kayit)}). Odak dağıtıcının fiyatı rakibe göre **{new_relation}**.\n\n'
                f'**İşaretli fiyat farkı:** Odak dağıtıcı fiyatından rakip fiyatı çıkarılır. '
                f'Önce **{fmt(r.ilk_fark,signed=True)} TL**, şimdi **{fmt(r.son_fark,signed=True)} TL**; '
                f'farktaki değişim **{fmt(r.fark_degisimi,signed=True)} TL**. Negatif değer odak firma fiyatının '
                f'rakipten düşük, pozitif değer yüksek olduğunu gösterir.\n\n'
                f'**Mutlak fark:** {fmt(abs(r.ilk_fark))} TL → {fmt(abs(r.son_fark))} TL '
                f'({fmt(r.mutlak_fark_degisimi,signed=True)} TL). Bu iki fiyat arasındaki uzaklıktır; iyi/kötü anlamı taşımaz.\n\n'
                f'**Bu iki tarih arasında geçerli fiyatların net değişimi:** {anchor} '
                f'{fmt(r.baz_degisim_tl,signed=True)} TL (%{fmt(r.baz_degisim_pct,signed=True)}); {r.firma} '
                f'{fmt(r.rakip_degisim_tl,signed=True)} TL (%{fmt(r.rakip_degisim_pct,signed=True)}). '
                f'Değişim oranları arasındaki fark **{fmt(r.yuzde_puan_farki,signed=True)} yüzde puan**.\n\n'
                f'**Son doğrulanmış fiyat geçişleri:** {anchor}: {last_event(r.il,anchor)} '
                f'{r.firma}: {last_event(r.il,r.firma)}\n\n'
                f'*Not: Karşılaştırma tarihleri, iki şirketin aynı gün zam/indirim yaptığı anlamına gelmez; '
                f'ilan edilmiş son geçerli fiyatlar kullanılır.*')
        else:
            explanation=(f'**{r.il} · {fuel}:** Başlangıç gününde iki firmadan birinin fiyatı '
                         f'yoktur. Bitişte {anchor} {fmt(r.baz_son_fiyat)} TL, '
                         f'{r.firma} {fmt(r.son_fiyat)} TL; fark {fmt(r.son_fark,signed=True)} TL.')
        if pd.notna(r.ilk_fark) and r.ilk_fark*r.son_fark < -EPS:
            kind='Fiyat sıralaması değişti'; icon='🔀'; prio=0
        elif pd.notna(r.ilk_fark) and abs(r.mutlak_fark_degisimi)>=threshold:
            kind='Fiyat uzaklığı arttı' if r.mutlak_fark_degisimi>0 else 'Fiyat uzaklığı azaldı';icon='📏';prio=1
        elif pd.notna(r.ilk_fark) and abs(r.fark_degisimi)>=threshold:
            kind='Fiyat farkı değişti';icon='↔️';prio=2
        elif abs(r.rakip_degisim_tl)>=threshold or abs(r.baz_degisim_tl)>=threshold:
            kind='Dönemsel fiyat hareketi';icon='📊';prio=3
        else:
            continue
        results.append({'Simge':icon,'Başlık':kind,'İl':r.il,'Rakip':r.firma,
                        'Öncelik':prio,'Açıklama':explanation,'Fark Değişimi (TL)':r.fark_degisimi,
                        'Önceki Fark (TL)':r.ilk_fark,'Son Fark (TL)':r.son_fark,
                        'Mutlak Fark Değişimi (TL)':r.mutlak_fark_degisimi,
                        'Etki':abs(float(r.fark_degisimi)) if pd.notna(r.fark_degisimi) else 0})
    findings=pd.DataFrame(results)
    if not findings.empty:
        findings=findings.sort_values(['Öncelik','Etki','İl','Rakip'],ascending=[True,False,True,True]).head(max_results).reset_index(drop=True)
    return findings,periods


def pair_relation_flow(periods):
    if periods.empty:return pd.DataFrame(columns=['ilk','son','adet'])
    d=periods.dropna(subset=['ilk_fark','son_fark']).copy()
    if d.empty:return pd.DataFrame(columns=['ilk','son','adet'])
    def relation(s):
        return np.select([s< -EPS,s > EPS],['Odak fiyat daha düşük','Odak fiyat daha yüksek'],default='Eşit fiyat')
    d['ilk']=relation(d['ilk_fark']);d['son']=relation(d['son_fark'])
    return d.groupby(['ilk','son'],as_index=False).size().rename(columns={'size':'adet'})


def transition_acceleration(data, fuel, companies, cities, beginning, ending):
    """Son iki GERÇEK fiyat hareketinin yön ve büyüklük karşılaştırması.
    İlk fiyat kaydı ve değişmeyen tekrarlar dışarıda tutulur.
    """
    d=data[data['yakit'].eq(fuel)&data['firma'].isin(companies)&data['tarih'].le(pd.Timestamp(ending))]
    if cities:d=d[d['il'].isin(cities)]
    d=true_changes(d)
    cols=['İl','Firma','Önceki Hareket Tarihi','Son Hareket Tarihi','Önceki Hareket (TL)',
          'Son Hareket (TL)','Önceki Hareket (%)','Son Hareket (%)',
          'Oran Farkı (Yüzde Puan)','Tutar Farkı (TL)']
    if d.empty:return pd.DataFrame(columns=cols)
    keys=['il','firma']
    d=d.sort_values(['il','firma','tarih']).copy()
    d['önceki_tarih']=d.groupby(keys)['tarih'].shift()
    d['önceki_hareket_tl']=d.groupby(keys)['degisim_tl'].shift()
    d['önceki_hareket_pct']=d.groupby(keys)['degisim_yuzde'].shift()
    d=d.sort_values('tarih').drop_duplicates(keys,keep='last')
    d=d[d['önceki_tarih'].notna() & d['tarih'].ge(pd.Timestamp(beginning))]
    if d.empty:return pd.DataFrame(columns=cols)
    d=d.rename(columns={'il':'İl','firma':'Firma','önceki_tarih':'Önceki Hareket Tarihi',
                        'tarih':'Son Hareket Tarihi','önceki_hareket_tl':'Önceki Hareket (TL)',
                        'degisim_tl':'Son Hareket (TL)','önceki_hareket_pct':'Önceki Hareket (%)',
                        'degisim_yuzde':'Son Hareket (%)'})
    d['Oran Farkı (Yüzde Puan)']=d['Son Hareket (%)']-d['Önceki Hareket (%)']
    d['Tutar Farkı (TL)']=d['Son Hareket (TL)']-d['Önceki Hareket (TL)']
    return d[cols].sort_values('Oran Farkı (Yüzde Puan)',key=lambda a:a.abs(),ascending=False).reset_index(drop=True)
