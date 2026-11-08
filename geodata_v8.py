# -*- coding: utf-8 -*-
"""Folium haritaları: tamamı yerelde hesaplanan etkin fiyatları gösterir.
Türkiye il poligonları açık ODbL kaynaktan indirilip dosya olarak önbelleğe alınır.
İnternet/GeoJSON yoksa il merkezlerinde etkileşimli işaretçiler gösterilir.
"""
from __future__ import annotations
import html
import json
from functools import lru_cache
from pathlib import Path
import requests
import folium
from folium.plugins import Fullscreen, MiniMap
import pandas as pd
import numpy as np
from engine import norm
from advanced_engine import fmt, day_str

GEO_PATH=Path(__file__).with_name('turkiye_iller.geojson')
GEO_URLS=[
    'https://raw.githubusercontent.com/theaiagent/turkiye_iller_geojson/main/turkiye_iller.geojson',
    'https://github.com/theaiagent/turkiye_iller_geojson/raw/refs/heads/main/turkiye_iller.geojson',
]

# Harita geometrisi ulaşılamadığında 81 ilde yine etkileşimli işaretçiler gösterebilmek için merkezler.
CITY_CENTERS={
'ADANA':(37.00,35.32),'ADIYAMAN':(37.76,38.28),'AFYONKARAHİSAR':(38.75,30.54),
'AĞRI':(39.72,43.05),'AMASYA':(40.65,35.83),'ANKARA':(39.93,32.86),
'ANTALYA':(36.89,30.71),'ARTVİN':(41.18,41.82),'AYDIN':(37.85,27.85),
'BALIKESİR':(39.65,27.88),'BİLECİK':(40.14,29.98),'BİNGÖL':(38.88,40.50),
'BİTLİS':(38.40,42.10),'BOLU':(40.73,31.61),'BURDUR':(37.71,30.28),
'BURSA':(40.18,29.06),'ÇANAKKALE':(40.15,26.41),'ÇANKIRI':(40.60,33.62),
'ÇORUM':(40.55,34.96),'DENİZLİ':(37.77,29.08),'DİYARBAKIR':(37.92,40.23),
'EDİRNE':(41.68,26.56),'ELAZIĞ':(38.67,39.22),'ERZİNCAN':(39.75,39.49),
'ERZURUM':(39.90,41.27),'ESKİŞEHİR':(39.77,30.52),'GAZİANTEP':(37.06,37.38),
'GİRESUN':(40.92,38.39),'GÜMÜŞHANE':(40.46,39.47),'HAKKARİ':(37.57,43.74),
'HATAY':(36.20,36.16),'ISPARTA':(37.76,30.55),'MERSİN':(36.80,34.63),
'İSTANBUL':(41.01,28.97),'İZMİR':(38.42,27.14),'KARS':(40.60,43.10),
'KASTAMONU':(41.38,33.78),'KAYSERİ':(38.72,35.48),'KIRKLARELİ':(41.73,27.22),
'KIRŞEHİR':(39.15,34.16),'KOCAELİ':(40.77,29.93),'KONYA':(37.87,32.48),
'KÜTAHYA':(39.42,29.98),'MALATYA':(38.35,38.31),'MANİSA':(38.61,27.43),
'KAHRAMANMARAŞ':(37.58,36.93),'MARDİN':(37.32,40.73),'MUĞLA':(37.21,28.36),
'MUŞ':(38.75,41.50),'NEVŞEHİR':(38.62,34.71),'NİĞDE':(37.97,34.68),
'ORDU':(40.99,37.87),'RİZE':(41.02,40.52),'SAKARYA':(40.77,30.39),
'SAMSUN':(41.28,36.33),'SİİRT':(37.93,41.95),'SİNOP':(42.03,35.15),
'SİVAS':(39.75,37.02),'TEKİRDAĞ':(40.98,27.51),'TOKAT':(40.32,36.55),
'TRABZON':(41.00,39.72),'TUNCELİ':(39.11,39.55),'ŞANLIURFA':(37.16,38.79),
'UŞAK':(38.68,29.41),'VAN':(38.49,43.38),'YOZGAT':(39.82,34.80),
'ZONGULDAK':(41.46,31.80),'AKSARAY':(38.37,34.03),'BAYBURT':(40.26,40.22),
'KARAMAN':(37.18,33.23),'KIRIKKALE':(39.85,33.52),'BATMAN':(37.88,41.14),
'ŞIRNAK':(37.52,42.46),'BARTIN':(41.63,32.34),'ARDAHAN':(41.11,42.70),
'IĞDIR':(39.92,44.04),'YALOVA':(40.65,29.27),'KARABÜK':(41.20,32.62),
'KİLİS':(36.72,37.12),'OSMANİYE':(37.07,36.25),'DÜZCE':(40.84,31.16),
}
ALIAS={'afyon':'afyonkarahisar','afyonkarahisar':'afyonkarahisar',
       'icel':'mersin','kahramanmaras':'kahramanmaras','k maras':'kahramanmaras',
       'hakkari':'hakkari'}

def city_key(name):
    key=norm(name)
    # Bazı Excel fiyat listeleri İstanbul'u Avrupa ve Anadolu olarak ayrı verir.
    # Haritada tek il geometrisi vardır; fiyatlar birleştirilmez, tooltip'te ayrı kalır.
    if key.startswith('istanbul') and ('avrupa' in key or 'anadolu' in key):
        return 'istanbul'
    return ALIAS.get(key,key)


@lru_cache(maxsize=1)
def get_geojson():
    """Yerel harita öncelikli; internet yalnız ilk indirmede kullanılır."""
    if GEO_PATH.exists():
        try:
            with GEO_PATH.open(encoding='utf8') as f: geo=json.load(f)
            if geo.get('type')=='FeatureCollection' and len(geo.get('features',[]))>=80:
                return geo,'Yerel GeoJSON'
        except (ValueError,OSError): pass
    for url in GEO_URLS:
        try:
            response=requests.get(url,timeout=4.5,headers={'User-Agent':'LikitgazPricingDashboard/5.0'})
            response.raise_for_status()
            geo=response.json()
            if geo.get('type')=='FeatureCollection' and len(geo.get('features',[]))>=80:
                try:GEO_PATH.write_text(json.dumps(geo,ensure_ascii=False),encoding='utf8')
                except OSError:pass
                return geo,'Açık GeoJSON'
        except (requests.RequestException,ValueError,TypeError):continue
    return None,'Harita sınırları indirilemedi; il merkezi işaretçileri kullanılıyor'


