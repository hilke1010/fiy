# -*- coding: utf-8 -*-
""" Harita, Tek Matris ve Yönetici Analizi.

"""
from __future__ import annotations
import html
import hashlib
import inspect
import os
import re
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from engine import ingest, PRIMARY
from advanced_engine import true_changes, effective_snapshot, day_str,fmt
from labels_v8 import company_label,primary_first,DEFAULT_BRANDS
from comparison_v8 import build_matrix,period_comparison
from map_v8 import build_market_map
from excel_v8 import export_matrix
from shared_store import current_info, publish, read_source
from price_chart import change_dates, movement_series, price_chart
from relative_comparison import compare_transitions, explain_movement, plot_relative_history

st.set_page_config(page_title=' • Fiyat Karşılaştırma V1 Açık Kaynak Veri!!!',page_icon='🔷',layout='wide',initial_sidebar_state='collapsed')

BLUE='#388dff';RED='#ff5878';GREEN='#20dcb0';GOLD='#f4c96d'
st.markdown('''<style>
.block-container{max-width:1920px;padding-top:1.0rem;padding-bottom:3rem}
:root{--accent:#388dff}
[data-testid="stSidebar"]{background:#071a2b}
[data-testid="stMetric"]{background:linear-gradient(120deg,#123155,#0b253e);border:1px solid #274f75;border-radius:14px;padding:13px 17px}
[data-testid="stMetricValue"]{color:#9ccbff;font-size:25px;font-weight:850}
[data-testid="stDataFrame"]{border:1px solid #315477;border-radius:12px}
[data-testid="stRadio"] label{font-weight:700}
.stApp h1{letter-spacing:-.8px;font-size:2.05rem}
.stApp h2{font-size:1.4rem}
.hero{margin:8px 0 20px;background:linear-gradient(110deg,#0b2340 15%,#153d6d 65%,#0e3550);border-radius:18px;
border:1px solid #4b81b8;box-shadow:0 16px 45px #061523aa;padding:21px 28px;position:relative;overflow:hidden}
.hero:before{content:'';position:absolute;width:350px;height:350px;border-radius:50%;right:-110px;top:-190px;
background:radial-gradient(circle,#3b98ff44,#3b98ff00 65%);animation:halo 8s ease-in-out infinite alternate}
@keyframes halo{from{transform:translate(-20px,5px);opacity:.5}to{transform:translate(15px,30px);opacity:1}}
.hero h1{color:#fff;margin:2px 0 8px;font-size:28px;position:relative}.hero p{color:#c1daf6;margin:0;position:relative}
.hero .tag{font:850 11px Segoe UI,Arial;color:#83bfff;letter-spacing:2px;position:relative}
.head{margin:8px 0 14px;background:linear-gradient(100deg,#0d2b4b,#143c64);padding:16px 20px;
border-left:4px solid #4398ff;border-radius:12px}.head h2{margin:0;font-size:22px;color:white}
.head p{margin:5px 0 0;color:#a9c9e9;font-size:13px}
.kpi-note{background:#10365b;border:1px solid #315e89;border-radius:10px;padding:11px 13px;color:#c9e4ff;margin:7px 0 14px}
.pill{display:inline-block;padding:6px 11px;border:1px solid #275c93;background:#153961;border-radius:9px;
font:700 12px Segoe UI,Arial;color:#d9efff;margin:2px 5px 2px 0}
.legend{display:inline-block;padding:7px 11px;border:1px solid #3a5f7e;background:#0c253b;border-radius:8px;
font:700 12px Segoe UI,Arial;margin:3px 7px 3px 0}
.insight{background:linear-gradient(105deg,#0b2d50,#0c1f36);padding:16px 18px;border-radius:13px;border:1px solid #316397;margin:11px 0}
.insight strong{color:#d4eaff}.insight small{color:#bad2e8}
.chart-mini{border:1px solid #396b9b;border-radius:13px;background:linear-gradient(130deg,#0a2139,#123254);
  padding:12px 16px;min-height:116px;margin:7px 0 12px;box-shadow:0 7px 22px #02101d55}
.chart-mini .firm{font-size:13px;color:#bed8f0;font-weight:800;letter-spacing:.3px}
.chart-mini .val{font-size:24px;color:#f4faff;font-weight:950;margin-top:5px}
.chart-mini .movement{font-size:12px;color:#a9c5df;margin-top:4px}
</style>''',unsafe_allow_html=True)


def section(title,description,icon='◈'):
    st.markdown(f'<div class="head"><h2>{icon} {html.escape(title)}</h2><p>{html.escape(description)}</p></div>',unsafe_allow_html=True)


def source_pin():
    try:saved=st.secrets.get('UPLOAD_PIN',None)
    except Exception:saved=None
    return str(os.getenv('LIKITGAZ_UPLOAD_PIN') or saved or '1969')


def auth():
    if st.session_state.get('auth_v9'):return
    st.title('🔒 Likitgaz Veri Erişimi')
    st.caption('Excel yükleme ve rapor görüntüleme için erişim kodunu giriniz.')
    with st.form('pinform'):
        val=st.text_input('Erişim kodu',type='password')
        ok=st.form_submit_button('Giriş yap',use_container_width=True,type='primary')
    if ok:
        if val==source_pin():st.session_state['auth_v9']=True;st.rerun()
        else:st.error('Erişim kodu hatalı.')
    st.stop()


@st.cache_data(max_entries=3,ttl=3600,show_spinner=False)
def parse_upload(raw_bytes,filename):
    return ingest(raw_bytes,filename)


@st.cache_data(max_entries=4,show_spinner=False)
def parse_shared(digest, path, filename, source_mode):
    """Ortak dosyayı yalnız sürüm değiştiğinde oku; yerel/kayıtlı ayrımını koru."""
    return read_source({
        'sha256': digest,
        'path': path,
        'original_name': filename,
        'mode': source_mode,
    })




@st.cache_data(max_entries=16,show_spinner=False,ttl=1200)
def cached_comparison(revision, _data, city, fuel, rivals, start, end, only_likitgaz):
    """Dosya revizyonu değişmeden fiyat geçişlerini yeniden hesaplama."""
    return compare_transitions(_data, city, fuel, rivals, start, end, only_likitgaz)


@st.cache_data(max_entries=16, show_spinner=False, ttl=1800)
def cached_map_last_movements(revision, fuel, when, _data):
    """Yalnız hesaplanmış son fiyat hareketleri önbellekte tutulur.

    Folium/Leaflet harita nesnesi farklı kullanıcılar arasında PAYLAŞILMAZ.
    Bu ayrım aynı ağdaki iki tarayıcının haritayı bozmasını önler.
    """
    relevant = _data[(_data.yakit == fuel) & (_data.tarih <= pd.Timestamp(when))]
    if relevant.empty:
        return {}
    movements = true_changes(relevant)
    if movements.empty:
        return {}
    last = movements.sort_values('tarih', kind='stable').drop_duplicates(
        ['il', 'firma'], keep='last')
    return {(str(r.il), str(r.firma)): (float(r.degisim_tl), pd.Timestamp(r.tarih))
            for r in last.itertuples(index=False)}


def cached_folium_map(revision, fuel, mode, when, companies, rival,
                      labels, previous_date, show_previous,
                      _snapshot, _earlier, _data):
    """Her oturuma yepyeni Folium nesnesi; görünüm ve bilgi kartları aynı."""
    movements = cached_map_last_movements(revision, fuel, when, _data)
    # V9 harita modülünün eski sürümleri `last_changes` parametresini bilmeyebilir.
    # Uyum kontrolü, güncel orijinal haritada tüm ayrıntıları korur;
    # eski map_v8.py ile de TypeError oluşmasını engeller.
    kwargs = dict(
        labels=labels,
        price_history=None,
        previous_snapshot=_earlier,
        previous_date=previous_date,
        show_previous=show_previous,
    )
    if 'last_changes' in inspect.signature(build_market_map).parameters:
        kwargs['last_changes'] = movements
    return build_market_map(
        _snapshot, mode, fuel, when, companies, rival, **kwargs
    )


def brands_for(data,product):
    return primary_first(data.loc[data.yakit.eq(product),'firma'].dropna().unique().tolist())


def default_rivals(product,companies):
    preferred=DEFAULT_BRANDS if 'otogaz' in str(product).casefold() else ['Aygaz','İpragaz']
    avail=[c for c in companies if c!=PRIMARY]
    return [c for c in avail if company_label(c) in preferred] or avail[:5]


def real_dates(data):
    """Yalnız gerçek fiyat hareketi günleri; ilk kayıtlar geçiş sayılmaz."""
    changes=true_changes(data)
    return [pd.Timestamp(d).normalize() for d in sorted(changes.tarih.unique())] if not changes.empty else []


def date_selector(dates,prefix):
    """Matris için sade tarih seçimi; önceki dönem kendi checkbox'ıyla açılır."""
    if not dates:
        return None
    choice=st.selectbox('Karşılaştırma tarihi', ['Son kayıtlı fiyat geçişi', 'Tarih seç'],
                        key=prefix+'period')
    if choice=='Son kayıtlı fiyat geçişi':
        return dates[-1]
    return st.selectbox('Gerçek fiyat değişim tarihi',dates,index=len(dates)-1,
                        format_func=day_str,key=prefix+'which')


def matrix_html(matrix,details):
    """Tüm dönemler aynı tabloda, üç satırlı sticky başlık ve sabit il sütunu."""
    if matrix.empty or not len(matrix.columns):return '<p>Tablo oluşturulamadı.</p>'
    mcols=list(matrix.columns)
    prod=list(dict.fromkeys(x[0] for x in mcols))
    row1='<tr><th class="cityhead" rowspan="3">İL</th>'
    for i,p in enumerate(prod):
        width=sum(x[0]==p for x in mcols)
        row1+=f'<th class="top g{i%4}" colspan="{width}">{html.escape(p)}</th>'
    row1+='</tr>'
    row2='<tr>'
    spans=[]
    for f,p,b in mcols:
        if spans and spans[-1][0]==f and spans[-1][1]==p:spans[-1][2]+=1
        else:spans.append([f,p,1])
    for fuel,firm,n in spans:
        label='🔵 Likitgaz' if firm=='Likitgaz' else firm
        row2+=f'<th class="firm {"ref" if firm=="Likitgaz" else ""}" colspan="{n}">{html.escape(label)}</th>'
    row2+='</tr>'
    row3='<tr>'
    for fuel,firm,phase in mcols:
        klass='phase old' if phase.startswith('Önceki') else 'phase diff' if phase=='Fark değişimi' else 'phase'
        row3+=f'<th class="{klass}">{html.escape(phase)}</th>'
    row3+='</tr>'
    rows=[]
    for city,series in matrix.iterrows():
        cells=f'<td class="city">{html.escape(str(city))}</td>'
        for (fuel,firm,phase),v in series.items():
            if pd.isna(v):txt='—';cl='missing'
            elif firm=='Likitgaz':txt=fmt(v);cl='base' if phase=='Güncel fiyat' else 'base-old'
            elif phase=='Fark değişimi':txt=fmt(v,signed=True);cl='delta'
            else:txt=fmt(v,signed=True);cl='red' if v<0 else 'green' if v>0 else 'same'
            tip=html.escape(details.get((city,fuel,firm,phase),'Kayıt bulunamadı'),quote=True)
            cells+=f'<td class="num {cl}" title="{tip}">{txt}</td>'
        rows.append('<tr>'+cells+'</tr>')
    css='''<style>
    body{font-family:Segoe UI,Arial,sans-serif;background:#071727;color:#e6f0ff;margin:0}
    .view{height:700px;overflow:auto;border:1px solid #416b96;border-radius:13px;box-shadow:0 16px 36px #0006}
    table{border-collapse:separate;border-spacing:0;min-width:100%;font-size:12.6px;font-variant-numeric:tabular-nums}
    th,td{text-align:center;white-space:nowrap;border-bottom:1px solid #294a68;border-right:1px solid #274761;padding:9px 12px}
    th{position:sticky;z-index:3;background:#173650;color:#eaf5ff;font-weight:800}
    .top{top:0;height:42px;z-index:6;font-size:15px;color:white}
    .g0{background:#12529d}.g1{background:#087c72}.g2{background:#58468b}.g3{background:#0b7192}
    .firm{top:42px;height:38px;z-index:5;background:#173b60;font-size:13px}
    .firm.ref{background:#1c5596;color:white}
    .phase{top:80px;height:39px;z-index:4;background:#1b3856;min-width:87px;font-size:11px}
    .phase.old{background:#344963;color:#e7dfcd}.phase.diff{background:#655026;color:#ffe8a4}
    .cityhead{left:0;top:0;z-index:9;min-width:140px;background:#0d2c4c;font-size:15px}
    tr:nth-child(odd){background:#0d1b2b}tr:nth-child(even){background:#0d253b}
    td.city{position:sticky;left:0;z-index:2;background:#133455;text-align:left;font-weight:900;min-width:140px;color:#e8f4ff}
    td.num{font-weight:800;min-width:93px}
    td.num.red{background:#552034;color:#ffb7c5}td.num.green{background:#064c43;color:#a2ffdf}
    td.num.base{background:#1b5399;color:#e5f4ff;font-weight:950}
    td.num.base-old{background:#264f7d;color:#cfe2f4}
    td.num.delta{background:#4b3b21;color:#ffdf9d}
    td.num.same{color:#c7d6e7}td.num.missing{color:#8399ad}
    td.num:hover{filter:brightness(1.3);box-shadow:inset 0 0 0 2px #90ccff;cursor:help}
    </style>'''
    return css+'<div class="view"><table><thead>'+row1+row2+row3+'</thead><tbody>'+''.join(rows)+'</tbody></table></div>'


def city_comparison(snapshot,prev,city,companies):
    current=snapshot[snapshot['il'].eq(city)].set_index('firma')
    old=prev[prev['il'].eq(city)].set_index('firma') if prev is not None else pd.DataFrame()
    ref=float(current.loc[PRIMARY,'fiyat']) if PRIMARY in current.index else np.nan
    oldref=float(old.loc[PRIMARY,'fiyat']) if not old.empty and PRIMARY in old.index else np.nan
    rows=[]
    for firm in companies:
        if firm not in current.index:continue
        pr=float(current.loc[firm,'fiyat'])
        gap=ref-pr if np.isfinite(ref) else np.nan
        before=float(old.loc[firm,'fiyat']) if not old.empty and firm in old.index else np.nan
        old_gap=oldref-before if np.isfinite(oldref) and np.isfinite(before) else np.nan
        rows.append({'Dağıtıcı':company_label(firm),'Fiyat (TL)':pr,
                     'Güncel fark (TL)':gap,'Önceki fark (TL)':old_gap,
                     'Fark değişimi (TL)':gap-old_gap if np.isfinite(old_gap) else np.nan,
                     'Kayıt tarihi':day_str(current.loc[firm,'tarih'])})
    return pd.DataFrame(rows)



# Rapor görüntüleme: tüm yerel ağ kullanıcılarına açıktır.
# Veri güncelleme: yalnız PIN bilen yöneticiye açıktır.
with st.sidebar:
    st.markdown('### 📡 Ortak Fiyat Veri Kaynağı')
    info=current_info()
    if info:
        st.success('🟢 Ortak Excel etkin')
        row_info = (f'{info["valid_rows"]:,} kayıt' if info.get('valid_rows') is not None
                    else 'Klasörden otomatik yükleniyor')
        st.caption(f'📄 {info["original_name"]} · {row_info}')
        st.caption(f'🕒 Son güncelleme: {info.get("saved_at","—")}')
    else:
        st.info('Henüz ortak Excel yok. `fiyat.xlsx` dosyasını `app.py` yanına koyun veya aşağıdan yayımlayın.')
    st.caption('Açık Kaynak Veri!  `fiyat.xlsx` Exceli değiştirmek yeterlidir , Değiştirmek için benimle iletişime geçebilirsiniz :) , Veri yenileme süresi 5 dakika  .')
    with st.expander('🔐 Yönetici: Yeni Excel yayımla',expanded=False):
        pin=st.text_input('Excel güncelleme kodu',type='password',key='v9_admin_pin')
        if pin == source_pin():
            uploaded=st.file_uploader('Excel / CSV',type=['xlsx','xls','csv'],
                            help='Dosya, güncelle düğmesine basınca tüm oturumlar için yayımlanır.')
            if st.button('📤 Excel’i tüm kullanıcılar için güncelle',type='primary',
                         disabled=(uploaded is None),use_container_width=True):
                try:
                    with st.spinner('Dosya doğrulanıyor ve ortak kaynağa kaydediliyor...'):
                        updated=publish(uploaded.getvalue(), uploaded.name)
                    st.session_state['upload_notice']=(
                        f'{updated["original_name"]} yayımlandı; {updated["valid_rows"]:,} satır.')
                    st.session_state['shared_revision_seen']=updated['sha256']
                    st.rerun()
                except Exception as ex:
                    st.error(f'Yüklenemedi. Önceki veriler korundu: {ex}')
        elif pin:
            st.error('Güncelleme kodu yanlış.')
        else:
            st.caption('.....')
    if 'upload_notice' in st.session_state:
        st.success(st.session_state.pop('upload_notice'))

st.markdown('<div class="hero"><span class="tag">Fiyat Karsilastirma v1</span>'
  '<h1>🔷  ·  AÇIK KAYNAK VERİ ! FİYAT KARŞILAŞTIRMA MERKEZİ</h1>'
  '<p>Türkiye haritası &nbsp; • &nbsp; Tek dönemsel fark matrisi &nbsp; • &nbsp;  Yönetici analizi</p></div>',unsafe_allow_html=True)
if info is None:
    st.info('**En kolay yol:** `fiyat.xlsx` dosyasını `app.py` ile aynı klasöre koyun. Başka işlem gerekmez; tüm cihazlar aynı dosyayı görür. İsterseniz soldan dosya yükleyip de yayımlayabilirsiniz.')
    st.markdown('<span class="legend">🔴 Negatif: Likitgaz daha düşük</span>'
        '<span class="legend">🟢 Pozitif: Likitgaz daha yüksek</span>'
        '<span class="legend">🔵 Likitgaz referans fiyatı</span>',unsafe_allow_html=True)
    st.stop()
st.session_state.setdefault('shared_revision_seen',info['sha256'])
#watch_shared_file()
try:
    with st.spinner('Güncel ortak fiyat verisi okunuyor...'):
        data,quality=parse_shared(info['sha256'],info['path'],info['original_name'],info.get('mode','published'))
except Exception as ex:
    st.error(f'Ortak Excel okunamadı: {ex}')
    st.stop()
if data.empty:
    st.warning('Geçerli kayıt bulunamadı.')
    st.stop()
products_all=sorted(data.yakit.unique().tolist(),key=lambda x:(not any(x.casefold().startswith(n) for n in ['otogaz','dökme','mix','propan']),x))
companies_all=primary_first(data.firma.unique().tolist())
cities_all=sorted(data.il.unique().tolist())
default_products=[p for p in products_all if any(key in p.casefold() for key in ['otogaz','mix','propan'])] or products_all[:1]
st.markdown(''.join(f'<span class="pill">{html.escape(s)}</span>' for s in [f'{len(data):,} geçerli kayıt',f'{len(cities_all)} il',f'{len(products_all)} ürün',f'{len(companies_all)} dağıtıcı']),unsafe_allow_html=True)
if quality.get('catisan_gun',0):st.warning(f'{quality["catisan_gun"]} adet il/ürün/firma/tarih grubunda çelişen fiyatlar bulundu; Excel içindeki son kayıt alındı.')

pages=['🗺️ TÜRKİYE FİYAT HARİTASI','▦ FİYAT FARKI MATRİSİ','🧠 YÖNETİCİ MAKİNE ANALİZİ']
page=st.radio('Bölüm',pages,horizontal=True,label_visibility='collapsed')

if page==pages[0]:
    show_previous=st.checkbox('Önceki geçişi de göster',value=False,key='v9_map_previous_first')
    section('Türkiye İl Bazında Fiyat Haritası',
       'Tek büyük harita · seçilen geçiş tarihindeki yürürlükteki fiyatlar · isteğe bağlı önceki dönem karşılaştırması','🗺️')
    c1,c2=st.columns([1.1,2.9])
    with c1:product=st.selectbox('Harita ürünü',products_all,key='v9_map_product')
    choices=brands_for(data,product)
    with c2:companies=st.multiselect('Karşılaştırılacak dağıtıcılar',choices,
        default=primary_first(([PRIMARY] if PRIMARY in choices else [])+default_rivals(product,choices)),
        format_func=company_label,key='v9_map_companies')
    companies=primary_first(list(dict.fromkeys([PRIMARY]+companies)))
    dates=real_dates(data[data.yakit.eq(product)&data.firma.isin(companies)])
    if not dates:st.info('Ürün için karşılaştırılabilir fiyat geçiş kaydı bulunamadı.');st.stop()
    when=dates[-1]
    c4,c5=st.columns([1.3,1.9])
    with c4:mode=st.selectbox('Harita görünümü',['Likitgaz farkı','En yüksek','En düşük'],key='v9_map_mode')
    rivals=[c for c in companies if c!=PRIMARY]
    with c5:rival=st.selectbox('Haritada fiyat farkı hangi rakiple?',rivals,
         format_func=company_label,key='v9_map_rival',disabled=(mode!='Likitgaz farkı')) if rivals else None
    show_labels=st.checkbox('En yüksek/en düşük görünümünde dağıtıcı isimleri',value=False,key='v9_map_labels')
    pos=dates.index(when);prev_date=dates[pos-1] if pos>0 else None
    snapshot=effective_snapshot(data,when,fuel=product,companies=companies)
    earlier=effective_snapshot(data,prev_date,fuel=product,companies=companies) if show_previous and prev_date is not None else None
    if show_previous and prev_date is None:
        st.info('Seçilen geçiş tarihinden daha önce karşılaştırılabilir gerçek fiyat değişim tarihi bulunmuyor.')
    if snapshot.empty:st.info('Seçilen tarihte fiyat kaydı yok.');st.stop()
    if mode=='Likitgaz farkı' and (rival is None or PRIMARY not in snapshot.firma.unique()):
        st.info('Likitgaz farkı için Likitgaz ve en az bir rakip fiyatı gereklidir.');st.stop()
    cities=sorted(snapshot.il.unique().tolist())
    st.markdown('<div class="kpi-note">🔵 <b>Harita karşılaştırması:</b> Fark = Likitgaz fiyatı − rakip fiyatı. '
       '<span style="color:#ff9bb1">Negatif: Likitgaz düşük</span> · '
       '<span style="color:#76f3d0">Pozitif: Likitgaz yüksek</span>. '
       'İl üzerine gelindiğinde seçilen dağıtıcıların fiyatları görüntülenir.</div>',unsafe_allow_html=True)
    with st.spinner('Türkiye il haritası hazırlanıyor...'):
        fmap,status=cached_folium_map(info['sha256'],product,mode,when,tuple(companies),rival,
           show_labels,prev_date,show_previous,snapshot,earlier,data)
    try:
        # Filtre/dosya değişirse eski Leaflet iframe'i yeniden kullanılmasın.
        map_signature = (info['sha256'], product, mode, str(when),
                         tuple(companies), rival, show_labels, show_previous,
                         str(prev_date) if show_previous else '')
        map_key = 'v9_country_map_' + hashlib.sha1(
            repr(map_signature).encode('utf-8')).hexdigest()[:16]
        event=st_folium(fmap,height=770,width=None,key=map_key,
           returned_objects=['last_object_clicked_popup','last_object_clicked_tooltip'])
    except Exception:
        st.warning('Etkileşimli harita bileşeni açılamadı; harita HTML olarak gösteriliyor.')
        st.components.v1.html(fmap.get_root().render(),height=770,scrolling=False)
        event={}
    if event:
        raw=str(event.get('last_object_clicked_popup') or event.get('last_object_clicked_tooltip') or '')
        match=re.search(r'data-city="([^"]+)"',raw)
        selected_city=html.unescape(match.group(1)) if match else None
        if selected_city in cities:st.session_state['map_city_v9_next']=selected_city
    section('Seçili İlin Fiyat Farkı Detayı',
        'Haritada bir ile tıklayın veya il seçin. Önceki fiyat farkı yalnız kutu işaretlendiğinde gösterilir.','📍')
    proposed=st.session_state.pop('map_city_v9_next',None)
    if proposed in cities:st.session_state['map_city_v9']=proposed
    elif 'map_city_v9' in st.session_state and st.session_state['map_city_v9'] not in cities:
        st.session_state['map_city_v9']=cities[0]
    city=st.selectbox('İl seçiniz',cities,index=cities.index('KAYSERİ') if 'KAYSERİ' in cities else 0,key='map_city_v9')
    report=city_comparison(snapshot,earlier,city,companies)
    if not report.empty:
        pri=report[report['Dağıtıcı']=='Likitgaz']
        if not pri.empty:st.metric(f'{city} · Likitgaz geçerli fiyatı',fmt(pri.iloc[0]['Fiyat (TL)'])+' TL')
        columns=['Dağıtıcı','Fiyat (TL)','Güncel fark (TL)']
        if show_previous and earlier is not None:columns+=['Önceki fark (TL)','Fark değişimi (TL)']
        columns+=['Kayıt tarihi']
        shown=report[columns].copy()
        sty=shown.style.format({c:'{:+.2f}' for c in ['Güncel fark (TL)','Önceki fark (TL)'] if c in shown.columns},na_rep='—')
        sty=sty.format({c:'{:.2f}' for c in ['Fiyat (TL)'] if c in shown.columns},na_rep='—')
        if 'Fark değişimi (TL)' in shown:sty=sty.format({'Fark değişimi (TL)':'{:+.2f}'},na_rep='—')
        sty=sty.map(lambda v:('color:#fb9aad;background-color:#542234' if v<0 else
                              'color:#70ebc8;background-color:#16493f' if v>0 else '') if pd.notna(v) else '',
                     subset=['Güncel fark (TL)'] + (['Önceki fark (TL)'] if 'Önceki fark (TL)' in shown else []))
        st.dataframe(sty,use_container_width=True,hide_index=True,height=min(560,80+42*len(shown)))

    # YENİ: Mutlak fiyatların birbirine yakınlığı yerine, sıfır çizgisi
    # üzerinden Likitgaz'ın rakibin üstünde/altında olduğu dönemler vurgulanır.
    section('Likitgaz / Rakip Fiyat Sıralaması · Dönemsel Geçişler',
        'Sıfırın altı: Likitgaz daha düşük (kırmızı). Sıfırın üstü: Likitgaz daha yüksek (yeşil). '
        'Altın yıldız: iki şirketin fiyat sıralaması değişti.','📈')
    available_rivals=[x for x in companies if x!=PRIMARY and x in choices]
    suggested=[x for x in available_rivals if company_label(x) in ('Aygaz','İpragaz')]
    default_rivals_chart=(suggested or available_rivals[:2])[:2]
    left,right=st.columns([2.5,2.0])
    with left:
        chart_rivals=st.multiselect('Grafikte karşılaştırılacak rakipler', available_rivals,
            default=default_rivals_chart,format_func=company_label,key='v9_chart_rivals',
            max_selections=6)
    with right:
        event_mode=st.radio('Geçişlerin kaynağı',
            ['Likitgaz geçişleri','Seçilen tüm şirketlerin geçişleri'],
            index=0,horizontal=True,key='v9_cross_event_mode')
    if chart_rivals:
        only_likitgaz=(event_mode=='Likitgaz geçişleri')
        event_brands=[PRIMARY] if only_likitgaz else [PRIMARY]+chart_rivals
        possible=change_dates(data,city,product,event_brands)
        if possible:
            if len(possible)>1:
                range_tag=hashlib.sha1(repr((city,product,event_mode,tuple(chart_rivals))).encode('utf8')).hexdigest()[:10]
                first,last=st.select_slider('Karşılaştırma aralığı · yalnız gerçek fiyat geçişleri',
                    options=possible,value=(possible[max(0,len(possible)-14)],possible[-1]),
                    format_func=day_str,key='v9_cross_range_'+range_tag)
            else:
                first=last=possible[0]
                st.caption('Bu kapsamda tek gerçek fiyat geçişi var: '+day_str(last))
            gap_history,comparison_events,_ = cached_comparison(
                info['sha256'],data,city,product,tuple(chart_rivals),first,last,only_likitgaz)
            if gap_history.empty:
                st.info('Bu tarihlerde karşılaştırma için iki şirkette de geçerli fiyat bulunamadı.')
            else:
                fig=plot_relative_history(gap_history,comparison_events,city,product)
                st.plotly_chart(fig,use_container_width=True,
                                config={'displaylogo':False,'scrollZoom':False})
                real_cross=(comparison_events[comparison_events['durum'].isin([
                    'Üstünden altına geçti','Altından üstüne geçti'])]
                    .sort_values('tarih',ascending=False)) if not comparison_events.empty else comparison_events
                st.markdown('#### 🔁 Fiyat sıralamasının değiştiği tarihler')
                if real_cross.empty:
                    st.caption('Seçili geçişlerde Likitgaz ile bu rakiplerin fiyat sıralaması değişmemiştir. '
                               'Fiyat farkının büyüklüğü yine değişmiş olabilir.')
                else:
                    st.markdown(f'**{len(real_cross)} fiyat sıralaması geçişi** tespit edildi. '
                                'Altın yıldızlar bu tarihleri gösterir.')
                    for _,ev in real_cross.head(8).iterrows():
                        with st.container(border=True):
                            st.markdown('**⚡ '+html.escape(company_label(ev['firma']))+' · '
                                        +html.escape(ev['durum'])+'**')
                            st.markdown(explain_movement(ev,city,product))
                if not comparison_events.empty:
                    st.markdown('#### 📋 Son iki kontrol tarihine göre şirket bazında fark')
                    for firm in chart_rivals:
                        q=comparison_events[comparison_events.firma.eq(firm)].sort_values('tarih')
                        if q.empty:continue
                        current=q.iloc[-1]
                        with st.expander(f'{company_label(firm)} · '
                                         f'{fmt(current["onceki_fark"],signed=True)} TL → '
                                         f'{fmt(current["son_fark"],signed=True)} TL · '
                                         f'{current["durum"]}',expanded=False):
                            st.markdown(explain_movement(current,city,product))
                with st.expander('Tüm gerçek geçişleri tablo olarak incele',expanded=False):
                    if not comparison_events.empty:
                        detail=comparison_events.sort_values('tarih',ascending=False).copy()
                        detail['Rakip']=detail['firma'].map(company_label)
                        detail['Tarih']=detail['tarih'].dt.strftime('%d.%m.%Y')
                        detail['Önceki kontrol']=detail['onceki_tarih'].dt.strftime('%d.%m.%Y')
                        table=detail.rename(columns={
                            'onceki_ref':'Likitgaz önceki','son_ref':'Likitgaz güncel',
                            'onceki_rakip':'Rakip önceki','son_rakip':'Rakip güncel',
                            'onceki_fark':'Önceki fark','son_fark':'Güncel fark',
                            'fark_degisim':'Fark değişimi','durum':'Sıralama'})
                        st.dataframe(table[['Tarih','Önceki kontrol','Rakip',
                            'Likitgaz önceki','Likitgaz güncel','Rakip önceki',
                            'Rakip güncel','Önceki fark','Güncel fark','Fark değişimi','Sıralama']],
                            hide_index=True,use_container_width=True)
                if st.toggle('Eski görünüm: şirketlerin TL fiyat basamaklarını da göster',
                             value=False,key='v9_show_old_step_chart'):
                    points,movements=movement_series(data,city,product,
                        [PRIMARY]+chart_rivals,first,last)
                    if not points.empty:
                        pricefig=price_chart(points,[PRIMARY]+chart_rivals,city,product)
                        st.plotly_chart(pricefig,use_container_width=True,
                            config={'displaylogo':False,'scrollZoom':False})
        else:
            st.info('Seçilen firmaların gerçek fiyat değişim kaydı bulunamadı.')
    else:
        st.info('En az bir rakip seçin; Likitgaz her zaman otomatik karşılaştırılır.')

elif page==pages[1]:
    section('Tek Tabloda Çok Ürünlü Fiyat Farkları',
       'Güncel fiyatlar · isteğe bağlı önceki fiyat/fark ve değişim sütunları · tek profesyonel Excel sayfası','▦')
    products=st.multiselect('Tabloya alınacak ürünler',products_all,default=default_products,key='v9_matrix_products')
    if not products:st.info('En az bir ürün seçiniz.');st.stop()
    company_map={}
    with st.expander('⚙️ Ürüne özel rakip sütunlarını düzenleyin',expanded=False):
        for fuel in products:
            avail=[x for x in brands_for(data,fuel) if x!=PRIMARY]
            company_map[fuel]=st.multiselect(f'{fuel} dağıtıcıları',avail,
                default=default_rivals(fuel,avail),format_func=company_label,key='v9_cols_'+fuel)
    used=primary_first([PRIMARY]+[co for p in products for co in company_map.get(p,[])])
    dates=real_dates(data[data.yakit.isin(products)&data.firma.isin(used)])
    if not dates:st.info('Gerçek fiyat geçiş tarihi yok.');st.stop()
    r1,r2=st.columns([2.1,1.5])
    with r1:when=date_selector(dates,'v9matrix')
    with r2:show_previous=st.checkbox('Önceki dönemi aynı tabloya ekle',value=False,key='v9_previous_in_same')
    pos=dates.index(when);prev_date=dates[pos-1] if pos>0 else None
    if show_previous and prev_date is None:
        st.warning('Bu karşılaştırma tarihinde önceki geçiş kaydı bulunamadı; önceki sütunlar eklenmeyecek.')
    selected_prev=prev_date if show_previous else None
    matrix,detail=build_matrix(data,products,company_map,when,selected_prev)
    st.markdown('<div class="kpi-note"><b>Fark = Likitgaz − rakip.</b> '
       '<span style="color:#ff9aae">Eksi / kırmızı: Likitgaz daha düşük.</span> '
       '<span style="color:#70edc9">Artı / yeşil: Likitgaz daha yüksek.</span> '
       f'Güncel: <b>{day_str(when)}</b>'
       +(f' · Önceki: <b>{day_str(selected_prev)}</b>' if selected_prev is not None else '')
       +'. Hücre üzerinde bekleyerek fiyat ve kayıt tarihini görebilirsiniz.</div>',unsafe_allow_html=True)
    st.components.v1.html(matrix_html(matrix,detail),height=715,scrolling=False)
    try:
        excel=export_matrix(matrix,when,selected_prev)
        st.download_button('📥 Renkli ve biçimlendirilmiş Excel raporunu indir',data=excel,
            file_name=f'Likitgaz_Fiyat_Karsilastirma_{pd.Timestamp(when):%Y%m%d}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',type='primary')
    except Exception as ex:st.error('Excel raporu oluşturulamadı: '+str(ex))
    st.caption('Önceki dönem açıksa aynı tabloda her rakip için Güncel fark, Önceki fark ve Fark değişimi gösterilir. Ayrı ikinci tablo veya Excel sayfası açılmaz.')

else:
    section('Yönetici İçin Makine Analizi',
       'Seçilen iki geçiş dönemi arasındaki fiyat farkları, geçerli kayıt tarihleri ve fiyat hareketlerinin tarafsız açıklaması','🧠')
    a,b=st.columns([1.0,1.9])
    with a:products=st.multiselect('Ürün / segment',products_all,default=default_products[:1],key='v9_manager_products')
    with b:companies=st.multiselect('Karşılaştırılacak dağıtıcılar',companies_all,
          default=primary_first(([PRIMARY] if PRIMARY in companies_all else []) + default_rivals(default_products[0],companies_all)),
          format_func=company_label,key='v9_manager_companies')
    c,d=st.columns([1.3,1.7])
    with c:cities=st.multiselect('İl (boş bırakılırsa tüm iller)',cities_all,default=[],key='v9_manager_cities')
    with d:mode_text=st.selectbox('Karşılaştırma türü',
        ['Likitgaz ile seçilen rakipler','Seçilen tüm dağıtıcı çiftleri','Seçili odak firma ile rakipler'],key='v9_manager_mode')
    mode={'Likitgaz ile seçilen rakipler':'Likitgaz',
          'Seçilen tüm dağıtıcı çiftleri':'Tümü',
          'Seçili odak firma ile rakipler':'Odak'}[mode_text]
    focus=PRIMARY
    if mode=='Odak':focus=st.selectbox('Odak dağıtıcı',companies,format_func=company_label,key='v9_manager_focus') if companies else PRIMARY
    if not products or len(companies)<2:st.info('Bir ürün ve en az iki şirket seçiniz.');st.stop()
    selected=primary_first(list(dict.fromkeys([PRIMARY]+companies))) if mode=='Likitgaz' else companies
    filtered=data[data.yakit.isin(products)&data.firma.isin(selected)]
    if cities:filtered=filtered[filtered.il.isin(cities)]
    dates=real_dates(filtered)
    if len(dates)<2:st.info('Bu seçimin iki ayrı fiyat geçiş tarihi yok.');st.stop()
    earlier,later=st.select_slider('Karşılaştırılacak gerçek geçiş dönemleri',options=dates,
        value=(dates[-2],dates[-1]),format_func=day_str,key='v9_manager_dates')
    if earlier==later:st.info('İki farklı geçiş tarihi seçiniz.');st.stop()
    with st.spinner('Dönemler arası fiyat farkları hesaplanıyor...'):
        result=period_comparison(data,products,selected,cities,earlier,later,mode,focus)
    if result.empty:st.info('Her iki geçiş döneminde fiyatı bulunan karşılaştırılabilir dağıtıcı çifti yok.');st.stop()
    s1,s2,s3,s4=st.columns(4)
    s1.metric('İncelenen firma çifti',len(result))
    s2.metric('Fiyat sıralaması değişen',int(result['Yön_Değişti'].sum()))
    s3.metric('Mutlak fiyat farkı artan',int((result['Mutlak_Değişim']>.001).sum()))
    s4.metric('Mutlak fiyat farkı azalan',int((result['Mutlak_Değişim']<-.001).sum()))
    st.markdown('<div class="kpi-note">📍 <b>Dönem okuma:</b> '
       'Fark, referans şirketin fiyatından rakip fiyatının çıkarılmasıyla bulunur. '
       'Likitgaz karşılaştırmasında referans daima Likitgaz’dır. '
       'Farkın büyüklüğü veya işareti iyi/kötü olarak yorumlanmaz.</div>',unsafe_allow_html=True)
    st.markdown('### 📑 Dönemsel Fiyat Farkı Analizleri')
    st.caption('Bulgular fiyat farkındaki mutlak değişim büyüklüğüne göre sıralanır. Açıklamalar seçilen dönemlerde geçerli olan gerçek kayıtlara dayanır.')
    maxn=min(30,len(result))
    limit=st.slider('Görüntülenecek analiz sayısı',1,maxn,min(12,maxn),key='v9_manager_limit')
    for i,r in result.head(limit).iterrows():
        aa=company_label(r['Referans']);bb=company_label(r['Rakip'])
        old=r['Önceki_Fark'];new=r['Güncel_Fark'];delta=r['Fark_Değişimi']
        symbol='↔️' if r['Yön_Değişti'] else '📊'
        color='#ffb2bd' if delta < -1e-7 else '#8ef1d3' if delta > 1e-7 else '#c8d7ea'
        st.markdown(
            '<div class="insight">'
            f'<div style="font-weight:900;font-size:16px;color:#e5f4ff">{symbol} '
            f'{html.escape(str(r["İl"]))} · {html.escape(str(r["Ürün"]))} · '
            f'{html.escape(aa)} / {html.escape(bb)}</div>'
            '<div style="display:flex;flex-wrap:wrap;gap:11px;margin-top:10px;font-size:13px">'
            f'<span>Önceki: <b>{fmt(old,signed=True)} TL</b></span>'
            f'<span>Güncel: <b>{fmt(new,signed=True)} TL</b></span>'
            f'<span>Değişim: <b style="color:{color}">{fmt(delta,signed=True)} TL</b></span>'
            '</div></div>',unsafe_allow_html=True)
        with st.expander('Fiyatların ve farkın dönemler arasında nasıl değiştiğini inceleyin',expanded=(i==0)):
            st.markdown(r['Açıklama'])
    st.caption('Açıklamalar yüklenen fiyat kayıtları üzerinden üretilir. Sistem fiyatların ekonomik açıdan olumlu veya olumsuz olduğunu değerlendirmez.')
