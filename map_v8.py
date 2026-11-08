# -*- coding: utf-8 -*-
"""V9 tek sabit Türkiye haritası, detaylı güncel/önceki dönem tooltip'i.
Fark = Likitgaz - rakip (negatif kırmızı, pozitif yeşil).
"""
from __future__ import annotations
import html
import numpy as np
import pandas as pd
import folium
from folium.features import DivIcon
from folium.plugins import Fullscreen
from geodata_v8 import get_geojson, CITY_CENTERS, city_key
from engine import PRIMARY
from advanced_engine import fmt, day_str, true_changes
from labels_v8 import company_label, winner_by_city

PALETTE=['#3b92ff','#ff9955','#21d7bd','#d9b65d','#bd9aff','#ff759a','#66bedb','#8dd08c','#f3be7c','#9ca6ff','#c0d87a']


def gap_color(v,scale=1):
    if not pd.notna(v) or not np.isfinite(v):return '#53657b'
    if abs(float(v))<1e-7:return '#8798ad'
    weight=min(0.98,0.38+0.6*abs(v)/max(scale,0.1))
    red=(255,76,112);green=(22,208,166)
    target=red if v<0 else green
    base=(18,43,68)
    return '#%02x%02x%02x'%tuple(int(base[i]*(1-weight)+target[i]*weight) for i in range(3))


def tooltip_html(city,part,fuel,when,prior=None,prior_when=None,show_previous=False,last_changes=None):
    """Her şehir tooltip'inde tüm seçilen dağıtıcılar ve kayıt tarihleri.
    Eski fark sütunları yalnız checkbox ile açılır; ileri veri kullanılmaz.
    """
    current={r.firma:r for r in part.itertuples(index=False)}
    old={r.firma:r for r in prior.itertuples(index=False)} if prior is not None else {}
    lk=current.get(PRIMARY);reference=float(lk.fiyat) if lk else np.nan
    old_lk=old.get(PRIMARY);oldref=float(old_lk.fiyat) if old_lk else np.nan
    hi=part.loc[part.fiyat.eq(part.fiyat.max()),'firma'].tolist()
    lo=part.loc[part.fiyat.eq(part.fiyat.min()),'firma'].tolist()
    records=part.sort_values('fiyat',ascending=False)
    cols='<th>Dağıtıcı</th><th>Güncel (TL)</th><th>Likitgaz farkı</th>'
    if show_previous:cols+='<th>Önceki fark</th><th>Fark değişimi</th>'
    cols+='<th>Kayıt tarihi</th><th>Son zam / indirim</th>'
    lines=[]
    for r in records.itertuples(index=False):
        firm=r.firma;gap=reference-float(r.fiyat) if np.isfinite(reference) else np.nan
        previous=old.get(firm)
        old_gap=(oldref-float(previous.fiyat) if (previous is not None and np.isfinite(oldref)) else np.nan)
        delta=(gap-old_gap) if np.isfinite(gap) and np.isfinite(old_gap) else np.nan
        gap_color_css='#ff8da7' if gap<-1e-7 else '#6ceac9' if gap>1e-7 else '#d2ddea'
        def vnum(v):return fmt(v,signed=True)+' TL' if pd.notna(v) else '—'
        base_bg='#1a4787' if firm==PRIMARY else 'transparent'
        cells=(f'<td style="font-weight:800">{html.escape(company_label(firm))}</td>'
               f'<td style="text-align:right;font-weight:800">{fmt(r.fiyat)} TL</td>'
               f'<td style="text-align:right;color:{gap_color_css};font-weight:900">{vnum(gap)}</td>')
        if show_previous:
            past_tone='#ff8da7' if old_gap<-1e-7 else '#6ceac9' if old_gap>1e-7 else '#cbd9eb'
            cells+=(f'<td style="text-align:right;color:{past_tone};font-weight:800">{vnum(old_gap)}</td>'
                    f'<td style="text-align:right;color:#f3cf81;font-weight:800">{vnum(delta)}</td>')
        cells+=f'<td>{day_str(r.tarih)}</td>'
        movement=last_changes.get((city,firm)) if last_changes else None
        if movement:
            move_val,move_day=movement
            movement_color='#69f0cf' if move_val<0 else '#ffd18a' if move_val>0 else '#dceafd'
            cells+=(f'<td style="white-space:nowrap">'
                    f'<span style="display:inline-block;border-radius:5px;background:#163853;'
                    f'padding:4px 6px;font-weight:900;color:{movement_color}">'
                    f'{fmt(move_val,signed=True)} TL</span> '
                    f'<span style="font-size:10px;color:#b8cfea">{day_str(move_day)}</span></td>')
        else:cells+='<td>—</td>'
        lines.append(f'<tr style="background:{base_bg}">{cells}</tr>')
    prior_text=f' · Önceki dönem: {day_str(prior_when)}' if show_previous and prior_when is not None else ''
    title=(f'<div style="display:flex;align-items:center;justify-content:space-between;gap:10px">'
           f'<div style="font:900 21px Segoe UI,sans-serif;color:#9bcaff">{html.escape(city)}</div>'
           f'<div style="font-size:12px;color:#c7d9f0">{html.escape(fuel)} · {day_str(when)}</div></div>')
    hi_label=' / '.join(company_label(x) for x in hi)
    lo_label=' / '.join(company_label(x) for x in lo)
    summary=(f'<div style="display:flex;gap:6px;margin:9px 0;flex-wrap:wrap">'
       f'<span style="background:#244263;padding:6px 9px;border-radius:7px">En yüksek: <b>{html.escape(hi_label)}</b> · {fmt(part.fiyat.max())} TL</span>'
       f'<span style="background:#174d49;padding:6px 9px;border-radius:7px">En düşük: <b>{html.escape(lo_label)}</b> · {fmt(part.fiyat.min())} TL</span></div>')
    legend=('Fark = Likitgaz fiyatı − rakip fiyatı. <span style="color:#ff90a6">Negatif: Likitgaz daha düşük</span> · '
           '<span style="color:#76f1d1">Pozitif: Likitgaz daha yüksek</span>. '
           'Kayıt tarihi fiyatın değiştiği gün olmak zorunda değildir.')
    return (f'<div class="lk-map-card" data-city="{html.escape(city,quote=True)}" '
            f'style="background:#081b2f;color:#f0f8ff;border:1px solid #5c8cca;box-shadow:0 16px 44px #000b;'
            f'font:12px Segoe UI,Arial,sans-serif;padding:15px;border-radius:13px;'
            f'width:min(810px,calc(100vw - 80px));max-width:825px;box-sizing:border-box">'
            +title+summary+
            f'<div style="font-size:11px;color:#a6c9f6;margin-bottom:7px">Fiyat karşılaştırması{prior_text}</div>'
            f'<div style="max-height:365px;overflow:auto"><table style="width:100%;border-collapse:collapse">'
            f'<thead style="background:#23446a;color:#eef7ff;position:sticky;top:0"><tr>{cols}</tr></thead><tbody>'
            +''.join(lines)+'</tbody></table></div>'
            f'<div style="margin-top:10px;padding-top:8px;border-top:1px solid #396085;color:#aac6e4;font-size:11px">{legend}</div>'
            '</div>')


def map_legend(mode,when,fuel,rival,companies,palette,show_previous=False,prior_when=None):
    if mode=='Likitgaz farkı':
        key=('<div><span style="color:#ff4c70">■</span> Likitgaz daha düşük: negatif fark</div>'
             '<div><span style="color:#16d0a6">■</span> Likitgaz daha yüksek: pozitif fark</div>'
             '<div><span style="color:#a5b4c7">■</span> Eşit / karşılaştırma yapılamıyor</div>')
        heading=f'Likitgaz − {company_label(rival)}'
    else:
        heading=f'{mode} fiyatlı dağıtıcı'
        key=''.join(f'<div><span style="color:{palette.get(f,"#9baac2")}">■</span> {html.escape(company_label(f))}</div>' for f in companies[:12])
    note=f'<p style="margin:5px 0">Önceki: {day_str(prior_when)} · tooltip içinde</p>' if show_previous else ''
    return (f'<div style="position:fixed;bottom:25px;left:22px;z-index:1000;pointer-events:none;'
            'border:1px solid #537ea9;border-radius:13px;background:#071a30ea;'
            'padding:12px 15px;color:#f0f8ff;box-shadow:0 12px 36px #0009;'
            'font:12px Segoe UI,Arial,sans-serif;max-height:330px;overflow:auto">'
            f'<b style="font-size:15px;color:#9fcdff">{html.escape(heading)}</b><br>'
            f'<span style="color:#b6ccdf">{html.escape(fuel)} · {day_str(when)}</span>'
            f'<div style="margin-top:7px;line-height:1.65">{key}</div>{note}'
            '<div style="font-size:11px;color:#b7cadd;margin-top:4px">İl üzerinde bekleyin / tıklayın</div></div>')


def build_market_map(snapshot, mode, fuel, when, companies, rival=None, selected_city=None,
                     labels=False, price_history=None, previous_snapshot=None, previous_date=None,
                     show_previous=False, last_changes=None):
    """Harita konumu Türkiye'ye sınırlandırılmıştır; önceki dönem aynı tooltip'te.
    Önceki veri: en geç previous_date as-of alınmalı, gelecekteki fiyat asla kullanılmaz.
    """
    if snapshot.empty:return None,'Seçilen tarihte veri bulunamadı.'
    # Orijinal OpenStreetMap zeminini ve renkli il katmanını KORU.
    m=folium.Map(location=[39.05,35.08], zoom_start=6,min_zoom=5,max_zoom=10,
                 tiles='OpenStreetMap',prefer_canvas=True,zoom_control=True,
                 control_scale=True,max_bounds=False)
    # Harita ekranın dışına sürüklenmesin; yine Türkiye sınırları görülür.
    m.options['maxBounds'] = [[34.0, 23.0], [44.0, 48.0]]
    m.options['maxBoundsViscosity'] = 1.0
    m.fit_bounds([[35.7,25.5],[42.2,45.0]],max_zoom=6)
    Fullscreen(position='topright').add_to(m)
    m.get_root().html.add_child(folium.Element('''<style>
    .leaflet-container{background:#0b2540!important}
    .leaflet-tile-pane{filter:grayscale(0.75) saturate(.65) brightness(.72)}
    .leaflet-tooltip{background:transparent!important;border:0!important;box-shadow:none!important;padding:0!important;pointer-events:none!important}
    .lk-map-card th,.lk-map-card td{padding:8px 7px;border-bottom:1px solid #284763;text-align:left;white-space:nowrap}
    .leaflet-popup-content{margin:0!important;max-height:min(600px,80vh);overflow:auto}
    .leaflet-popup-content-wrapper{padding:0!important;border-radius:14px;background:transparent!important;box-shadow:none!important}
    </style>'''))
    geo,status=get_geojson()
    groups={str(city):q for city,q in snapshot.groupby('il')}
    prior_groups={str(city):q for city,q in previous_snapshot.groupby('il')} if show_previous and previous_snapshot is not None else {}
    palette={f:PALETTE[i%len(PALETTE)] for i,f in enumerate(companies)}
    palette[PRIMARY]='#3b92ff'
    winners=winner_by_city(snapshot,mode) if mode!='Likitgaz farkı' else pd.DataFrame()
    win_by={r['il']:r for _,r in winners.iterrows()} if not winners.empty else {}
    gap_by={}
    if mode=='Likitgaz farkı':
        for city,group in groups.items():
            l=group[group.firma.eq(PRIMARY)].fiyat
            r=group[group.firma.eq(rival)].fiyat
            gap_by[city]=(float(l.iloc[0]-r.iloc[0]) if len(l) and len(r) else np.nan)
    vals=[abs(x) for x in gap_by.values() if np.isfinite(x)]
    scale=max(.2,float(np.percentile(vals,85))) if vals else 1
    colors={}
    for city in groups:
        if mode=='Likitgaz farkı':colors[city]=gap_color(gap_by.get(city,np.nan),scale)
        else:
            win=win_by.get(city)
            colors[city]=('#63748d' if win is None else '#a5b4c7' if bool(win['esitlik'])
                           else palette.get(win['firma'],'#63748d'))
    history = last_changes if last_changes is not None else {}
    if last_changes is None and price_history is not None and len(price_history):
        relevant=price_history[(price_history.yakit==fuel)&(price_history.tarih<=pd.Timestamp(when))]
        ev=true_changes(relevant)
        if not ev.empty:
            recent=ev.sort_values('tarih').drop_duplicates(['il','firma'],keep='last')
            history={(r.il,r.firma):(float(r.degisim_tl),r.tarih) for r in recent.itertuples(index=False)}
    shape_lookup={city_key(x.get('properties',{}).get('il_adi','')):x for x in geo['features']} if geo is not None else {}
    # Bir ilin birden fazla fiyat bölgesi varsa poligonu üst üste çizmek yerine
    # tek il üzerinde her bölgenin fiyatlarını AYRI tooltip panellerinde göster.
    regions={}
    for city,g in groups.items():
        regions.setdefault(city_key(city),[]).append((city,g))
    for province,segments in regions.items():
        city,group=segments[0]
        cards=[]
        for segment_name,segment_rows in segments:
            cards.append(tooltip_html(segment_name,segment_rows,fuel,when,
                   prior_groups.get(segment_name),previous_date,show_previous,history))
        if len(cards)>1:
            card=('<div style="max-height:560px;overflow:auto;background:#092035;padding:8px;'
                  'border:1px solid #4f7cb2;border-radius:12px">'
                  '<div style="font:800 15px Segoe UI;color:#b9d8ff;padding:6px">'
                  'Aynı ilde birden fazla fiyat bölgesi · değerler birleştirilmemiştir</div>'
                  +''.join(cards)+'</div>')
        else:card=cards[0]
        tooltip=folium.Tooltip(card,sticky=True,opacity=.98,direction='auto')
        popup=folium.Popup(card,max_width=820)
        feature=shape_lookup.get(province)
        fill=colors[city] if len(segments)==1 else '#60718c'
        if feature:
            folium.GeoJson(feature,name=city,
                style_function=lambda f,color=fill:dict(fillColor=color,color='#d2eaff',weight=1.35,
                    opacity=.8,fillOpacity=.86),
                highlight_function=lambda f:dict(color='#ffffff',weight=3.6,fillOpacity=.98),
                tooltip=tooltip,popup=popup).add_to(m)
        else:
            xy=CITY_CENTERS.get(city)
            if xy is None:xy=next((v for k,v in CITY_CENTERS.items() if city_key(k)==province),None)
            if xy:
                folium.CircleMarker(xy,radius=7,weight=1.7,color='#d4edff',fill=True,
                    fill_color=fill,fill_opacity=.97,tooltip=tooltip,popup=popup).add_to(m)
        if labels and city in CITY_CENTERS and mode!='Likitgaz farkı' and len(segments)==1:
            win=win_by.get(city)
            if win is not None:
                lbl=('EŞİT' if win['esitlik'] else company_label(win['firma']))
                content=(f'<span style="font:900 9px Arial;color:white;white-space:nowrap;'
                         f'text-shadow:0 1px 3px black;pointer-events:none">{html.escape(lbl)}</span>')
                folium.Marker(CITY_CENTERS[city],icon=DivIcon(html=content)).add_to(m)
    m.get_root().html.add_child(folium.Element(map_legend(mode,when,fuel,rival,companies,palette,show_previous,previous_date)))
    # Streamlit bileşeninin boyutu telefon/masaüstü geçişinde değişebilir.
    # Yeniden boyut hesaplaması haritanın boş/gri kalma ihtimalini azaltır.
    map_var=m.get_name()
    m.get_root().script.add_child(folium.Element(f"""
    (function() {{
      // Folium bu kodu harita değişkeninden önce basabilir.
      // DOM yüklendikten sonra erişilmesi ReferenceError'u önler.
      function installResizeFix() {{
        var target = window['{map_var}'];
        if (!target) return;
        var init = function() {{
          target.invalidateSize({{animate:false,pan:false}});
        }};
        target.whenReady(function() {{
          setTimeout(init, 150);
          setTimeout(init, 850);
          if (typeof ResizeObserver !== 'undefined') {{
            var observer = new ResizeObserver(function() {{
              target.invalidateSize({{animate:false,pan:false}});
            }});
            observer.observe(target.getContainer());
          }}
        }});
      }}
      if (document.readyState === 'complete') {{
        setTimeout(installResizeFix, 0);
      }} else {{
        window.addEventListener('load', installResizeFix, {{once:true}});
      }}
    }})();
    """))
    return m,status
