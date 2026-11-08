# -*- coding: utf-8 -*-
"""Gerçek fiyat geçişleri üzerinde profesyonel, basamaklı Likitgaz/rakip grafiği."""
from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from engine import PRIMARY
from advanced_engine import fmt, day_str, true_changes
from labels_v8 import company_label

BLUE = '#50a8ff'
RIVALS = ['#ffbd70', '#3fe6ce', '#c29aff', '#f77da3', '#f1dc78', '#77d9eb', '#91d28b']
BG = '#0b1e34'


def change_dates(data, city, fuel, companies):
    q = data[data.il.eq(city) & data.yakit.eq(fuel) & data.firma.isin(companies)]
    ev = true_changes(q)
    return [pd.Timestamp(x).normalize() for x in sorted(ev.tarih.unique())]


def movement_series(data, city, fuel, companies, start, end):
    """Çıktı: (nokta kayıtları, gerçek fiyat geçişleri). İlk fiyat zam değildir.
    Her serinin başlangıcında, o tarihte geçerli fiyat kullanılır; sadece
    gerçek değişimlerde basamak ve belirgin işaretçi oluşur.
    """
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if end < start:
        raise ValueError('Bitiş tarihi başlangıç tarihinden önce olamaz.')
    subset = data[(data.il == city) & (data.yakit == fuel) & data.firma.isin(companies)]
    subset = subset[subset.tarih.le(end)].copy()
    all_points, all_events = [], []
    for firm in list(dict.fromkeys(companies)):
        q = subset[subset.firma.eq(firm)].sort_values('tarih', kind='stable')
        if q.empty:
            continue
        # Aynı gün farklı kayıtlar varsa ingest önceden sonuncusunu seçer.
        changes = true_changes(q)
        strictly_before = q[q.tarih.lt(start)]
        on_start_change = not changes[changes.tarih.eq(start)].empty
        if not strictly_before.empty:
            first = strictly_before.iloc[-1]
            current_price = float(first.fiyat)
            # Seçilen ilk geçiş günündeki dikey fiyat hareketi de görünmeli.
            # Bu nedenle ilk gün zam varsa referans fiyatı bir önceki güne çiz.
            anchor_date = start-pd.Timedelta(days=1) if on_start_change else start
            all_points.append({'firma':firm, 'tarih':anchor_date, 'fiyat':current_price,
                               'degisim':np.nan, 'degisim_pct':np.nan,'is_event':False,
                               'description':f'{company_label(firm)} · önceki geçerli fiyat: {fmt(current_price)} TL'})
        else:
            first = q.iloc[0]
            if first.tarih > end:continue
            current_price = float(first.fiyat)
            if first.tarih >= start:
                all_points.append({'firma':firm,'tarih':pd.Timestamp(first.tarih), 'fiyat':current_price,
                                   'degisim':np.nan,'degisim_pct':np.nan,'is_event':False,
                                   'description':f'{company_label(firm)} · ilk kayıt: {day_str(first.tarih)} · {fmt(current_price)} TL'})
        between=changes[changes.tarih.ge(start) & changes.tarih.le(end)].sort_values('tarih')
        for ev in between.itertuples(index=False):
            p=float(ev.fiyat)
            all_points.append({'firma':firm,'tarih':pd.Timestamp(ev.tarih),'fiyat':p,
                               'degisim':float(ev.degisim_tl),'degisim_pct':float(ev.degisim_yuzde),
                               'is_event':True,
                               'description':(f'{company_label(firm)}<br>{day_str(ev.tarih)} · ' 
                                              f'{fmt(ev.onceki_fiyat)} TL → <b>{fmt(p)} TL</b><br>'
                                              f'Değişim: {fmt(ev.degisim_tl,signed=True)} TL ' 
                                              f'({fmt(ev.degisim_yuzde,signed=True)}%)')})
            all_events.append({'Tarih':pd.Timestamp(ev.tarih), 'Dağıtıcı':company_label(firm),
                               'Firma kodu':firm,'Önceki fiyat (TL)':float(ev.onceki_fiyat),
                               'Yeni fiyat (TL)':p,'Değişim (TL)':float(ev.degisim_tl),
                               'Değişim (%)':float(ev.degisim_yuzde)})
            current_price=p
        last_date=max(pd.Timestamp(x['tarih']) for x in all_points if x['firma']==firm)
        if end > last_date:
            all_points.append({'firma':firm,'tarih':end,'fiyat':current_price,
                               'degisim':np.nan,'degisim_pct':np.nan,'is_event':False,
                               'description':f'{company_label(firm)} · {day_str(end)} itibarıyla {fmt(current_price)} TL'})
    points=pd.DataFrame(all_points,columns=['firma','tarih','fiyat','degisim','degisim_pct','is_event','description'])
    events=pd.DataFrame(all_events,columns=['Tarih','Dağıtıcı','Firma kodu','Önceki fiyat (TL)',
                                           'Yeni fiyat (TL)','Değişim (TL)','Değişim (%)'])
    return points,events


def _add_trace(fig, rec, firm, color, big=False, row=None, showlegend=True):
    # Markers only on real transition dates. The first point is a reference price.
    rec=rec.sort_values('tarih')
    sizes=[(13 if big else 9) if bool(b) else 0 for b in rec.is_event]
    trace=go.Scatter(
        x=rec['tarih'],y=rec['fiyat'],mode='lines+markers',name=company_label(firm),
        line=dict(color=color,width=4.8 if big else 2.5,shape='hv'),
        marker=dict(size=sizes, color=color, line=dict(color='#d8eeff' if big else '#132c44',width=1.4)),
        customdata=rec['description'],
        hovertemplate='%{customdata}<extra></extra>',
        showlegend=showlegend,
        opacity=1 if big else .90,
        connectgaps=False,
    )
    if row is None:
        fig.add_trace(trace)
    else:
        fig.add_trace(trace,row=row,col=1)


def price_chart(points, companies, city, fuel, separate=False):
    """Tek güçlü Likitgaz çizgisi, seçilen her rakip ayrı renk. İsteğe bağlı küçük paneller."""
    if points.empty:return None
    available=[f for f in companies if f in set(points.firma)]
    rivals=[f for f in available if f!=PRIMARY]
    if separate and rivals and PRIMARY in available:
        fig=make_subplots(rows=len(rivals),cols=1,shared_xaxes=True,
                          subplot_titles=[f'{company_label(PRIMARY)} / {company_label(f)}' for f in rivals],
                          vertical_spacing=min(.12,.23/len(rivals)))
        for i,firm in enumerate(rivals,1):
            _add_trace(fig,points[points.firma==PRIMARY],PRIMARY,BLUE,True,row=i,showlegend=i==1)
            _add_trace(fig,points[points.firma==firm],firm,RIVALS[(i-1)%len(RIVALS)],False,row=i,showlegend=True)
            fig.update_yaxes(title_text='TL',row=i,col=1,showgrid=True,gridcolor='#233a56')
        height=max(390,245*len(rivals))
    else:
        fig=go.Figure()
        for i,firm in enumerate(available):
            color=BLUE if firm==PRIMARY else RIVALS[rivals.index(firm)%len(RIVALS)]
            _add_trace(fig,points[points.firma==firm],firm,color,firm==PRIMARY)
        height=510
    fig.update_layout(
        template='plotly_dark', paper_bgcolor=BG,plot_bgcolor=BG,height=height,
        margin=dict(l=36,r=30,t=68,b=82),
        title=dict(text=f'<b>{city} · {fuel} · Fiyat geçişleri</b>',font=dict(size=19,color='#ecf5ff')),
        legend=dict(orientation='h',yanchor='top',y=-.13,x=0,font=dict(size=12,color='#e2eeff'),
                    bgcolor='rgba(8,25,43,.5)'),
        hovermode='closest',
        hoverlabel=dict(bgcolor='#122d4b',font=dict(color='white',size=13)),
        font=dict(family='Arial, sans-serif',color='#d4e4fa'),
    )
    fig.update_xaxes(title_text='Gerçek fiyat geçiş tarihleri',showgrid=True,gridcolor='#1d3451',
                     tickformat='%d.%m.%Y',tickangle=-25,showline=True,linecolor='#46658d',
                     rangeslider_visible=False)
    fig.update_yaxes(title_text='Fiyat (TL)',showgrid=True,gridcolor='#244260',zeroline=False,
                     tickformat='.2f',showline=True,linecolor='#46658d')
    return fig
