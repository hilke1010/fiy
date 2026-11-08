# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd

import shared_store
from engine import PRIMARY, ingest
from relative_comparison import compare_transitions, plot_relative_history, explain_movement

A='AYGAZ ANONİM ŞİRKETİ'
I='İPRAGAZ ANONİM ŞİRKETİ'

def frame():
    raw=pd.DataFrame([
        ('KAYSERİ',PRIMARY,'Otogaz',10.0,'2026-01-01'),
        ('KAYSERİ',PRIMARY,'Otogaz',10.0,'2026-01-03'),
        ('KAYSERİ',PRIMARY,'Otogaz',9.0,'2026-01-10'),
        ('KAYSERİ',PRIMARY,'Otogaz',10.5,'2026-01-20'),
        ('KAYSERİ',A,'Otogaz',9.0,'2026-01-01'),
        ('KAYSERİ',A,'Otogaz',9.2,'2026-01-10'),
        ('KAYSERİ',A,'Otogaz',9.5,'2026-01-18'),
        ('KAYSERİ',I,'Otogaz',10.2,'2026-01-01'),
        ('KAYSERİ',I,'Otogaz',10.2,'2026-01-19'),
    ],columns=['il','firma','yakit','fiyat','tarih'])
    raw['tarih']=pd.to_datetime(raw['tarih'])
    return raw

class TestRanking(unittest.TestCase):
    def test_likitgaz_focused_crossings(self):
        h,e,dates=compare_transitions(frame(),'KAYSERİ','Otogaz',[A,I],only_likitgaz=True)
        self.assertEqual([x.day for x in dates],[10,20])
        ay=e[e.firma.eq(A)].sort_values('tarih')
        self.assertEqual(ay['durum'].tolist(),['Üstünden altına geçti','Altından üstüne geçti'])
        self.assertAlmostEqual(ay.iloc[0]['onceki_fark'],1.0)
        self.assertAlmostEqual(ay.iloc[0]['son_fark'],-0.2)
        self.assertAlmostEqual(ay.iloc[1]['son_fark'],1.0)
        self.assertIn('likitgaz daha yüksek', explain_movement(ay.iloc[0],'KAYSERİ','Otogaz'))
        self.assertIn('Üstünden altına geçti', explain_movement(ay.iloc[0],'KAYSERİ','Otogaz'))
        fig=plot_relative_history(h,e,'KAYSERİ','Otogaz')
        self.assertIsNotNone(fig)
        self.assertTrue(any('star' in str(t.marker.symbol) for t in fig.data if t.type=='scatter' and t.marker))

    def test_all_events_add_rival_transition_and_no_false_event(self):
        _,e,dates=compare_transitions(frame(),'KAYSERİ','Otogaz',[A,I],only_likitgaz=False)
        self.assertEqual([x.day for x in dates],[10,18,20])
        self.assertNotIn(3,[x.day for x in dates])
        self.assertNotIn(19,[x.day for x in dates])
        self.assertEqual(len(e),6)

    def test_dates_do_not_use_future_prices(self):
        _,e,_=compare_transitions(frame(),'KAYSERİ','Otogaz',[A],
                                   start=pd.Timestamp('2026-01-10'),end=pd.Timestamp('2026-01-10'))
        self.assertAlmostEqual(e.iloc[0]['son_ref'],9)
        self.assertAlmostEqual(e.iloc[0]['son_rakip'],9.2)
        self.assertAlmostEqual(e.iloc[0]['onceki_rakip'],9)

    def test_missing_price_skips_false_comparison(self):
        d=frame()
        d=d[~d.firma.eq(A) | (d.tarih>=pd.Timestamp('2026-01-18'))]
        _,events,_=compare_transitions(d,'KAYSERİ','Otogaz',[A],only_likitgaz=True)
        self.assertEqual(len(events),0)

class TestLocalExcel(unittest.TestCase):
    def test_place_fiyat_in_app_folder_auto_load_and_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp); (path/'shared_data').mkdir()
            file=path/'fiyat.xlsx'
            rows=pd.DataFrame({
                'İl Adı':['KAYSERİ','KAYSERİ'],
                'Firma Adı':[PRIMARY,A],
                'Yakıt Tipi':['Otogaz','Otogaz'],
                'Fiyat':[52.00,53.00],
                'Geçerlilik Tarihi':[pd.Timestamp('2026-01-01')]*2,
            })
            rows.to_excel(file,index=False)
            with patch.object(shared_store,'ROOT',path), patch.object(shared_store,'DATA_DIR',path/'shared_data'):
                a=shared_store.current_info()
                self.assertEqual(a['mode'],'local')
                self.assertEqual(a['original_name'],'fiyat.xlsx')
                d,q=shared_store.read_source(a)
                self.assertEqual(len(d),2)
                self.assertAlmostEqual(d[d.firma.eq(PRIMARY)].fiyat.iloc[0],52)
                rows.at[0,'Fiyat']=53
                rows.to_excel(file,index=False)
                b=shared_store.current_info()
                self.assertNotEqual(a['sha256'],b['sha256'])
                d2,q2=shared_store.read_source(b)
                self.assertAlmostEqual(d2[d2.firma.eq(PRIMARY)].fiyat.iloc[0],53)

if __name__=='__main__':
    unittest.main()
