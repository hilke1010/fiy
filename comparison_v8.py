# -*- coding: utf-8 -*-
"""V8: Tüm rakip farkları = Likitgaz fiyatı - rakip fiyatı.
Negatif: Likitgaz daha düşük (kırmızı), pozitif: Likitgaz daha yüksek (yeşil).
"""
from __future__ import annotations
from itertools import combinations
import numpy as np
import pandas as pd
from engine import PRIMARY
from advanced_engine import effective_snapshot, true_changes, day_str, fmt
from labels_v8 import company_label, primary_first

EPS=1e-7


def price_difference(reference, competitor):
    return reference - competitor


def _series(pivot, company, cities):
    return pivot[company] if company in pivot else pd.Series(np.nan,index=cities)


def _one_snapshot(data, when, selected):
    return effective_snapshot(data,when,companies=selected)


def build_matrix(data,products,company_map,when,previous=None):
    """Tek DataFrame, 3-katlı başlık (ürün, firma, dönem), isteğe bağlı önceki fark.
    Dönem başlıkları: 'Güncel fark', 'Önceki fark', 'Fark değişimi', baz fiyatlar.
    """
    selected=set([PRIMARY])
    for product in products:selected.update(company_map.get(product,[]))
    current=_one_snapshot(data,when,list(selected))
    old=_one_snapshot(data,previous,list(selected)) if previous is not None else None
    cities=sorted(data['il'].dropna().unique().tolist())
    result=pd.DataFrame(index=pd.Index(cities,name='İl'))
    details={}
    for fuel in products:
        def get_piv(snap):
            part=snap[snap['yakit'].eq(fuel)] if snap is not None else pd.DataFrame()
            if part.empty:return pd.DataFrame(index=cities),pd.DataFrame(index=cities)
            return (part.pivot(index='il',columns='firma',values='fiyat').reindex(cities),
                    part.pivot(index='il',columns='firma',values='tarih').reindex(cities))
        p,dt=get_piv(current);b,bdt=get_piv(old)
        ref=_series(p,PRIMARY,cities);ref_old=_series(b,PRIMARY,cities)
        result[(fuel,'Likitgaz','Güncel fiyat')]=ref
        if previous is not None:
            result[(fuel,'Likitgaz','Önceki fiyat')]=ref_old
        for city in cities:
            details[(city,fuel,'Likitgaz','Güncel fiyat')]=(
                f'Likitgaz fiyatı: {fmt(ref.loc[city])} TL | Geçerli kayıt: '
                f'{day_str(dt.loc[city,PRIMARY] if PRIMARY in dt else pd.NaT)}')
            if previous is not None:
                details[(city,fuel,'Likitgaz','Önceki fiyat')]=(
                    f'Önceki Likitgaz fiyatı: {fmt(ref_old.loc[city])} TL | Geçerli kayıt: '
                    f'{day_str(bdt.loc[city,PRIMARY] if PRIMARY in bdt else pd.NaT)}')
        used=set()
        for firm in company_map.get(fuel,[]):
            if firm==PRIMARY:continue
            label=company_label(firm)
            if label in used:
                label=f'{label} ({firm[:8]})'
            used.add(label)
            price=_series(p,firm,cities);old_price=_series(b,firm,cities)
            gap=price_difference(ref,price)
            result[(fuel,label,'Güncel fark')]=gap
            if previous is not None:
                old_gap=price_difference(ref_old,old_price)
                result[(fuel,label,'Önceki fark')]=old_gap
                result[(fuel,label,'Fark değişimi')]=gap-old_gap
            for city in cities:
                current_txt=(f'{label} fiyatı: {fmt(price.loc[city])} TL '
                    f'({day_str(dt.loc[city,firm] if firm in dt else pd.NaT)}), '
                    f'Likitgaz fiyatı: {fmt(ref.loc[city])} TL '
                    f'({day_str(dt.loc[city,PRIMARY] if PRIMARY in dt else pd.NaT)}). '
                    f'Likitgaz − {label} = {fmt(gap.loc[city],signed=True)} TL.')
                details[(city,fuel,label,'Güncel fark')]=current_txt
                if previous is not None:
                    old_txt=(f'{label} önceki fiyatı: {fmt(old_price.loc[city])} TL '
                        f'({day_str(bdt.loc[city,firm] if firm in bdt else pd.NaT)}), '
                        f'Likitgaz önceki fiyatı: {fmt(ref_old.loc[city])} TL '
                        f'({day_str(bdt.loc[city,PRIMARY] if PRIMARY in bdt else pd.NaT)}). '
                        f'Önceki fark: {fmt(old_gap.loc[city],signed=True)} TL.')
                    details[(city,fuel,label,'Önceki fark')]=old_txt
                    details[(city,fuel,label,'Fark değişimi')]=(
                        f'{label}: {old_txt} Güncel: {current_txt} '
                        f'Fark değişimi = Güncel fark − Önceki fark = '
                        f'{fmt((gap-old_gap).loc[city],signed=True)} TL.')
    if result.shape[1]:
        result.columns=pd.MultiIndex.from_tuples(result.columns,names=['Ürün','Firma','Görünüm'])
    return result,details


def period_comparison(data, products, companies, cities, earlier, later, mode='Likitgaz', focus=PRIMARY):
    """Seçili iki GERÇEK piyasa geçiş tarihindeki etkin fiyatlar; yanlı yorum içermez.
    mode='Likitgaz' için referans daima PRIMARY; 'Tümü' her firma çifti;
    'Odak' kullanıcı firması - diğer firma.
    """
    earlier=pd.Timestamp(earlier).normalize();later=pd.Timestamp(later).normalize()
    if earlier>=later:return pd.DataFrame()
    companies=primary_first(list(dict.fromkeys(companies)))
    if mode=='Likitgaz': anchor=PRIMARY
    elif mode=='Odak':anchor=focus
    else:anchor=None
    if anchor is not None and anchor not in companies:companies=[anchor]+companies
    subset=data[data['yakit'].isin(products)&data['firma'].isin(companies)&data['tarih'].le(later)]
    if cities:subset=subset[subset['il'].isin(cities)]
    if subset.empty:return pd.DataFrame()
    s0=effective_snapshot(subset,earlier,companies=companies)
    s1=effective_snapshot(subset,later,companies=companies)
    if s0.empty or s1.empty:return pd.DataFrame()
    key=['il','yakit','firma']
    old=s0[key+['fiyat','tarih']].rename(columns={'fiyat':'before','tarih':'before_record'})
    now=s1[key+['fiyat','tarih']].rename(columns={'fiyat':'now','tarih':'now_record'})
    merged=old.merge(now,on=key,how='inner')
    ev=true_changes(subset)
    changes={}
    if not ev.empty:
        for r in ev.sort_values('tarih').drop_duplicates(['il','yakit','firma'],keep='last').itertuples(index=False):
            changes[(r.il,r.yakit,r.firma)]=r
    rows=[]
    for (city,fuel),group in merged.groupby(['il','yakit'],sort=False):
        by={r.firma:r for r in group.itertuples(index=False)}
        if anchor is None:pairs=list(combinations(primary_first(list(by.keys())),2))
        elif anchor in by:pairs=[(anchor,r) for r in primary_first(list(by)) if r!=anchor]
        else:pairs=[]
        for a,b in pairs:
            ra,rb=by[a],by[b]
            g0=float(ra.before-rb.before);g1=float(ra.now-rb.now);delta=g1-g0
            abschange=abs(g1)-abs(g0)
            cross=(g0*g1 < -EPS)
            def relation(g,now=False):
                if abs(g)<EPS:return 'aynı düzeydedir' if now else 'aynı düzeydeydi'
                verb=('yüksektir' if g>0 else 'düşüktür') if now else ('yüksekti' if g>0 else 'düşüktü')
                return f'{fmt(abs(g))} TL {verb}'
            def price_move(c0,c1,company):
                amount=float(c1-c0)
                if abs(amount)<EPS:return f'{company} fiyatı değişmedi'
                return f'{company} fiyatı {fmt(abs(amount))} TL {"arttı" if amount>0 else "azaldı"}'
            last_a=changes.get((city,fuel,a));last_b=changes.get((city,fuel,b))
            def record_note(r,ev):
                if ev is None:return 'Öncesine ait doğrulanmış başka zam/indirim kaydı yok'
                return (f'Son kayıtlı fiyat değişimi {day_str(ev.tarih)}: '
                        f'{fmt(ev.onceki_fiyat)} → {fmt(ev.fiyat)} TL '
                        f'({fmt(ev.degisim_tl,signed=True)} TL; '
                        f'%{fmt(ev.degisim_yuzde,signed=True)})')
            old_ref=day_str(ra.before_record);old_rival=day_str(rb.before_record)
            new_ref=day_str(ra.now_record);new_rival=day_str(rb.now_record)
            explanation=(
              f'**Önceki dönem ({day_str(earlier)}):** {company_label(a)} fiyatı '
              f'**{fmt(ra.before)} TL** (son geçerli kayıt {old_ref}); '
              f'{company_label(b)} fiyatı **{fmt(rb.before)} TL** (son geçerli kayıt {old_rival}). '
              f'{company_label(a)} fiyatı {company_label(b)} fiyatından **{relation(g0)}**. '
              f'Fark: **{fmt(g0,signed=True)} TL**.\n\n'
              f'**Güncel dönem ({day_str(later)}):** {company_label(a)} '
              f'**{fmt(ra.now)} TL** ({new_ref}); {company_label(b)} '
              f'**{fmt(rb.now)} TL** ({new_rival}). '
              f'{company_label(a)} fiyatı {company_label(b)} fiyatından **{relation(g1,now=True)}**. '
              f'Fark: **{fmt(g1,signed=True)} TL**.\n\n'
              f'**Fark değişimi:** {fmt(g0,signed=True)} TL → {fmt(g1,signed=True)} TL; '
              f'**{fmt(delta,signed=True)} TL**. İki şirket arasındaki mutlak fiyat mesafesi '
              f'{fmt(abs(abschange))} TL {"arttı" if abschange>EPS else "azaldı" if abschange<-EPS else "düzeyinde kaldı"}. '
              f'{price_move(ra.before,ra.now,company_label(a))}; '
              f'{price_move(rb.before,rb.now,company_label(b))}.\n\n'
              f'**Son fiyat değişimi kayıtları:** {company_label(a)}: {record_note(ra,last_a)}. '
              f'{company_label(b)}: {record_note(rb,last_b)}.\n\n'
              f'**Hesaplama:** Fark = {company_label(a)} − {company_label(b)}; '
              f'fark değişimi = güncel fark − önceki fark. '
              'Karşılaştırma günü bir fiyatın değiştirilmiş olmasını gerektirmez; '
              'o tarihe kadar yürürlükte olan son fiyat alınır.')
            rows.append(dict(
                İl=city,Ürün=fuel,Referans=a,Rakip=b, Önceki_Fark=g0,Güncel_Fark=g1,
                Fark_Değişimi=delta,Mutlak_Değişim=abschange,Yön_Değişti=cross,
                Referans_Önceki=float(ra.before),Referans_Güncel=float(ra.now),
                Rakip_Önceki=float(rb.before),Rakip_Güncel=float(rb.now),
                Önceki_Tarih=earlier,Güncel_Tarih=later,Açıklama=explanation))
    if not rows:return pd.DataFrame()
    return pd.DataFrame(rows).sort_values('Fark_Değişimi',key=lambda x:x.abs(),ascending=False).reset_index(drop=True)
