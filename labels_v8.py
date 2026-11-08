# -*- coding: utf-8 -*-
"""Yalnız firma adları, sıralama ve eşit-fiyat kontrolü; fiyat farkı yok."""
from __future__ import annotations
import numpy as np
import pandas as pd
from engine import PRIMARY, norm

SHORT = {
    'LİKİTGAZ DAĞITIM VE ENDÜSTRİ ANONİM ŞİRKETİ':'Likitgaz',
    'AYGAZ ANONİM ŞİRKETİ':'Aygaz',
    'İPRAGAZ ANONİM ŞİRKETİ':'İpragaz',
    'PETROL OFİSİ ANONİM ŞİRKETİ':'P.Ofisi',
    'SHELL & TURCAS PETROL ANONİM ŞİRKETİ':'Shell',
    'GÜZEL ENERJİ AKARYAKIT ANONİM ŞİRKETİ':'Total',
    'AYTEMİZ AKARYAKIT DAĞITIM ANONİM ŞİRKETİ':'Aytemiz',
    'AKPET AKARYAKIT DAĞITIM ANONİM ŞİRKETİ':'Akpet',
    'TP PETROL DAĞITIM ANONİM ŞİRKETİ':'TP',
    'BP PETROLLERİ ANONİM ŞİRKETİ':'BP',
}
DEFAULT_BRANDS = ['Aygaz','İpragaz','P.Ofisi','Shell','Total','Aytemiz','Akpet']


def company_label(company):
    if company in SHORT: return SHORT[company]
    key=norm(company)
    if key.startswith('akpet'): return 'Akpet'
    if key.startswith('total'): return 'Total'
    if key.startswith('petrol ofisi'): return 'P.Ofisi'
    if key.startswith('guzel enerji'): return 'Total'
    return company.split(' ANONİM')[0].title()[:34]


def primary_first(companies):
    return sorted(companies, key=lambda x: (x != PRIMARY, DEFAULT_BRANDS.index(company_label(x)) if company_label(x) in DEFAULT_BRANDS else 99, str(x)))



def winner_by_city(snapshot, mode='En yüksek'):
    """Seçili firmalar arasında uç fiyat; eşitlikleri gizlemez."""
    if snapshot.empty:return pd.DataFrame(columns=['il','firma','fiyat','tarih','esit_firmalar','esitlik'])
    v=snapshot.groupby('il')['fiyat'].transform('max' if mode=='En yüksek' else 'min')
    subset=snapshot.loc[np.isclose(snapshot['fiyat'],v,atol=1e-8)].sort_values(['il','firma'])
    rows=[]
    for city,g in subset.groupby('il'):
        rows.append({'il':city,'firma':g['firma'].iloc[0],
                     'fiyat':float(g['fiyat'].iloc[0]),'tarih':g['tarih'].iloc[0],
                     'esitlik':len(g)>1, 'esit_firmalar':list(g['firma'])})
    return pd.DataFrame(rows)


