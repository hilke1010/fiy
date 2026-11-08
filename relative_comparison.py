# -*- coding: utf-8 -*-
"""Likitgaz ile seçilen rakipler arasındaki fiyat sıralaması geçişleri.

Tarih bir fiyatın yürürlüğe girdiği gündür; her kontrol tarihinde o güne kadar
kayıtlı SON fiyat kullanılır. Bir önceki kontrol tarihi ile kıyas yapılır.
Fark = Likitgaz - rakip; negatif kırmızı / pozitif yeşil.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from engine import PRIMARY
from advanced_engine import day_str, fmt, true_changes
from labels_v8 import company_label

BLUE, RED, GREEN, GOLD = '#51a9ff', '#ff6588', '#25d6b0', '#ffd27b'
EPS = 0.005


def _status(gap):
    if pd.isna(gap):
        return 'Eksik fiyat'
    if gap < -EPS:
        return 'Likitgaz daha düşük'
    if gap > EPS:
        return 'Likitgaz daha yüksek'
    return 'Eşit fiyat'


def _transition(old, new):
    if pd.isna(old) or pd.isna(new):
        return 'Veri eksik'
    a, b = np.sign(round(float(old), 2)), np.sign(round(float(new), 2))
    if a > 0 and b < 0:
        return 'Üstünden altına geçti'
    if a < 0 and b > 0:
        return 'Altından üstüne geçti'
    if a and not b:
        return 'Fiyatlar eşitlendi'
    if not a and b:
        return 'Eşitlikten ayrıldı'
    return 'Sıralama aynı'


def compare_transitions(data, city, fuel, rivals, start=None, end=None,
                        only_likitgaz=True):
    """Çıktı: (gap_history, detailed_changes, dates).

    gap_history: firma,tarih,likitgaz_fiyat,rakip_fiyat,fark
    detailed_changes: iki kontrol tarihi arasındaki fark ve fiyat değişimi
    dates: uygun, yalnız gerçek geçiş tarihleri
    """
    rivals = [f for f in dict.fromkeys(rivals) if f != PRIMARY]
    empty_hist = pd.DataFrame(columns=['firma','tarih','likitgaz_fiyat','rakip_fiyat','fark'])
    empty_changes = pd.DataFrame(columns=['tarih','onceki_tarih','firma','onceki_ref','son_ref',
                                           'onceki_rakip','son_rakip','onceki_fark','son_fark',
                                           'fark_degisim','ref_degisim','rakip_degisim','durum'])
    if not rivals:
        return empty_hist, empty_changes, []
    focus = data.loc[data.il.eq(city) & data.yakit.eq(fuel) &
                     data.firma.isin([PRIMARY]+rivals), ['firma','tarih','fiyat']].copy()
    if focus.empty or PRIMARY not in set(focus.firma):
        return empty_hist, empty_changes, []
    focus['tarih'] = pd.to_datetime(focus['tarih']).dt.normalize()
    focus.sort_values(['firma','tarih'], inplace=True, kind='stable')
    # Fonksiyon diğer modüllerde firma bazında gruplanmasını bekler.
    changes = true_changes(focus.assign(il=city, yakit=fuel))
    if changes.empty:
        return empty_hist, empty_changes, []
    events = changes.loc[changes.firma.eq(PRIMARY)] if only_likitgaz else changes
    times = sorted(pd.Timestamp(t).normalize() for t in events.tarih.unique())
    if start is not None:
        times = [t for t in times if t >= pd.Timestamp(start).normalize()]
    if end is not None:
        times = [t for t in times if t <= pd.Timestamp(end).normalize()]
    if not times:
        return empty_hist, empty_changes, []

    # İlk geçişten bir gün öncesi gerçek geçmiş fiyatı karşılaştırmada görünmeli.
    anchor = times[0] - pd.Timedelta(days=1)
    checkpoints = pd.DatetimeIndex([anchor]+times)
    valid = focus[focus.tarih <= times[-1]]
    pivot = valid.pivot_table(index='tarih', columns='firma', values='fiyat', aggfunc='last')
    pivot = pivot.reindex(pivot.index.union(checkpoints)).sort_index().ffill().reindex(checkpoints)
    if PRIMARY not in pivot:
        return empty_hist, empty_changes, times
    hist, details = [], []
    for firm in rivals:
        if firm not in pivot:
            continue
        prev = None
        for t in checkpoints:
            reference = pivot.at[t, PRIMARY]
            competitor = pivot.at[t, firm]
            if not np.isfinite(reference) or not np.isfinite(competitor):
                continue
            curr = dict(firma=firm, tarih=pd.Timestamp(t),
                        likitgaz_fiyat=round(float(reference), 2),
                        rakip_fiyat=round(float(competitor), 2),
                        fark=round(float(reference-competitor), 2))
            hist.append(curr)
            if prev is not None:
                delta = round(curr['fark']-prev['fark'], 2)
                rd = round(curr['likitgaz_fiyat']-prev['likitgaz_fiyat'], 2)
                cd = round(curr['rakip_fiyat']-prev['rakip_fiyat'], 2)
                details.append(dict(tarih=curr['tarih'], onceki_tarih=prev['tarih'],
                                    firma=firm, onceki_ref=prev['likitgaz_fiyat'],
                                    son_ref=curr['likitgaz_fiyat'],
                                    onceki_rakip=prev['rakip_fiyat'],
                                    son_rakip=curr['rakip_fiyat'],
                                    onceki_fark=prev['fark'], son_fark=curr['fark'],
                                    fark_degisim=delta, ref_degisim=rd,
                                    rakip_degisim=cd, durum=_transition(prev['fark'],curr['fark'])))
            prev = curr
    return pd.DataFrame(hist, columns=empty_hist.columns), pd.DataFrame(details, columns=empty_changes.columns), times


def explain_movement(row, city, fuel):
    """Yorumdan kaçınan, iki dönemdeki fiyatları ve sıralamayı açıklayan metin."""
    brand = company_label(row['firma'])
    old_gap, new_gap = float(row['onceki_fark']), float(row['son_fark'])
    change = float(row['fark_degisim'])
    text = (f"**{city} · {fuel} · {brand} · {day_str(row['tarih'])}**  \n"
            f"Önceki kontrol tarihi **{day_str(row['onceki_tarih'])}**: Likitgaz "
            f"**{fmt(row['onceki_ref'])} TL**, {brand} **{fmt(row['onceki_rakip'])} TL**. "
            f"Fark **{fmt(old_gap,signed=True)} TL** ({_status(old_gap).lower()}).  \n"
            f"Son kontrol tarihi **{day_str(row['tarih'])}**: Likitgaz "
            f"**{fmt(row['son_ref'])} TL**, {brand} **{fmt(row['son_rakip'])} TL**. "
            f"Fark **{fmt(new_gap,signed=True)} TL** ({_status(new_gap).lower()}).  \n"
            f"İki kontrol arasında fark **{fmt(change,signed=True)} TL** değişti. "
            f"Likitgaz fiyatı **{fmt(row['ref_degisim'],signed=True)} TL**, "
            f"{brand} fiyatı **{fmt(row['rakip_degisim'],signed=True)} TL** değişti.")
    if row['durum'] != 'Sıralama aynı':
        text += f"  \n**Fiyat sıralaması: {row['durum']}.**"
    return text


def plot_relative_history(history, detail, city, fuel):
    """Rakip bazında ayrı paneller, sıfır çizgisi ve sıralama değişim işaretleri."""
    if history.empty:
        return None
    brands = [b for b in history.firma.unique()]
    n = len(brands)
    fig = make_subplots(rows=n, cols=1, shared_xaxes=True,
                        subplot_titles=[f'<b>{company_label(x)} · Likitgaz farkı</b>' for x in brands],
                        vertical_spacing=min(.10,.28/max(n,1)))
    for row, brand in enumerate(brands, 1):
        q = history.loc[history.firma.eq(brand)].sort_values('tarih')
        d = detail[detail.firma.eq(brand)] if not detail.empty else detail
        gap = q['fark'].astype(float).tolist()
        descriptions = [f'<b>{company_label(brand)}</b> · {day_str(r.tarih)}<br>'
                        f'Likitgaz: {fmt(r.likitgaz_fiyat)} TL · Rakip: {fmt(r.rakip_fiyat)} TL<br>'
                        f'<b>Fark: {fmt(r.fark,signed=True)} TL</b> · {_status(r.fark)}'
                        for r in q.itertuples(index=False)]
        fig.add_trace(go.Scatter(x=q.tarih, y=gap, mode='lines',
                       line=dict(color='#9bbfe5',width=3,shape='hv'),name=company_label(brand),
                       hoverinfo='skip',showlegend=False),row=row,col=1)
        for sign, color in [(-1,RED),(1,GREEN),(0,'#e4effe')]:
            mask = (q.fark.lt(-EPS) if sign == -1 else q.fark.gt(EPS) if sign == 1
                    else q.fark.abs().le(EPS))
            p=q[mask]
            if p.empty:continue
            idx=q.index.get_indexer(p.index)
            fig.add_trace(go.Scatter(x=p.tarih,y=p.fark,mode='markers',
                 marker=dict(size=10,color=color,line=dict(color='#edf7ff',width=1.3)),
                 text=[descriptions[j] for j in idx],
                 hovertemplate='%{text}<extra></extra>',name='Fark',showlegend=False),row=row,col=1)
        crossing = d[d.durum.isin(['Üstünden altına geçti','Altından üstüne geçti'])]
        if not crossing.empty:
            fig.add_trace(go.Scatter(x=crossing.tarih,y=crossing.son_fark,mode='markers',
                marker=dict(symbol='star',size=19,color=GOLD,line=dict(color='#fff5de',width=2)),
                text=[f'<b>FİYAT SIRALAMASI DEĞİŞTİ</b><br>{_transition(r.onceki_fark,r.son_fark)}<br>'
                      f'Önceki {fmt(r.onceki_fark,signed=True)} TL → Güncel {fmt(r.son_fark,signed=True)} TL'
                      for r in crossing.itertuples(index=False)],
                hovertemplate='%{text}<extra></extra>',name='Sıralama değişti',showlegend=row==1),row=row,col=1)
        fig.add_hline(y=0, line=dict(color='#f3d08b',width=2,dash='dash'),row=row,col=1)
        fig.update_yaxes(title_text='Fark (TL)',gridcolor='#234563',zeroline=False,
                         tickformat='+,.2f',row=row,col=1)
        # Her rakipte 0 çizgisini de gösteren görünür aralık.
        low, high = min(gap+[0]),max(gap+[0]); pad=max(.25,(high-low)*.2)
        fig.update_yaxes(range=[low-pad,high+pad],row=row,col=1)
    fig.update_layout(height=max(360,225*n+75),template='plotly_dark',
                      paper_bgcolor='#081a30',plot_bgcolor='#102742',
                      margin=dict(l=30,r=25,t=68,b=67),
                      font=dict(family='Arial, sans-serif',color='#e7f1ff',size=12),
                      title=dict(text=f'<b>{city} · {fuel} · Likitgaz / rakip fiyat farkının seyri</b>',
                                 font=dict(size=18)),
                      hoverlabel=dict(bgcolor='#0b243f',font=dict(size=13,color='white')),
                      legend=dict(orientation='h',y=-.06,x=0))
    fig.update_xaxes(tickformat='%d.%m.%Y',gridcolor='#1b3956',tickangle=-25,
                     rangeslider_visible=False)
    fig.update_xaxes(title_text='Gerçek fiyat geçiş tarihleri',row=n,col=1)
    return fig
