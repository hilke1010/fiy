# -*- coding: utf-8 -*-
"""V9 ortak veri + gerçek fiyat geçişleri için bağımsız testler.
Çalıştırma: python -m unittest test_shared_chart.py -v
"""
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from engine import ingest, PRIMARY
from advanced_engine import true_changes
from shared_store import publish, current_info, read_source
from price_chart import change_dates, movement_series, price_chart

AYGAZ='AYGAZ ANONİM ŞİRKETİ'
IPRAGAZ='İPRAGAZ ANONİM ŞİRKETİ'


def csv_bytes(rows):
    h='İl Adı;Firma Adı;Yakıt Tipi;Fiyat;Geçerlilik Tarihi\n'
    return (h + '\n'.join(';'.join(map(str,r)) for r in rows)).encode('utf-8-sig')


def sample():
    data=[
      ('KAYSERİ',PRIMARY,'Otogaz','51,00','01.01.2026'),
      ('KAYSERİ',PRIMARY,'Otogaz','51,00','05.01.2026'),  # duplicate price, NOT an event
      ('KAYSERİ',PRIMARY,'Otogaz','52,00','10.01.2026'),
      ('KAYSERİ',PRIMARY,'Otogaz','51,50','20.01.2026'),
      ('KAYSERİ',AYGAZ,'Otogaz','52,00','01.01.2026'),
      ('KAYSERİ',AYGAZ,'Otogaz','52,00','03.01.2026'),
      ('KAYSERİ',AYGAZ,'Otogaz','52,50','15.01.2026'),
      ('KAYSERİ',IPRAGAZ,'Otogaz','53,00','01.01.2026'),
      ('KAYSERİ',IPRAGAZ,'Otogaz','54,00','20.01.2026'),
    ]
    return csv_bytes(data)


class TestSharedData(unittest.TestCase):
    def test_other_sessions_see_latest_saved(self):
        with tempfile.TemporaryDirectory() as d:
            raw=sample()
            m=publish(raw,'fiyatlar.csv',d)
            self.assertEqual(m['raw_rows'],9)
            self.assertEqual(m['valid_rows'],9)
            self.assertEqual(current_info(d)['sha256'],m['sha256'])
            shared,quality=read_source(current_info(d))
            self.assertEqual(len(shared),9)
            self.assertEqual(quality['kullanilan'],9)
            self.assertEqual(Path(m['path']).read_bytes(),raw)

    def test_failed_import_does_not_replace_current(self):
        with tempfile.TemporaryDirectory() as d:
            old=publish(sample(),'valid.csv',d)
            with self.assertRaises(ValueError):
                publish(b'invalid file','bad.csv',d)
            self.assertEqual(old['sha256'],current_info(d)['sha256'])

    def test_version_switch(self):
        with tempfile.TemporaryDirectory() as d:
            one=publish(sample(),'first.csv',d)
            newraw=sample().replace(b'52,50',b'52,70')
            two=publish(newraw,'second.csv',d)
            self.assertNotEqual(one['sha256'],two['sha256'])
            self.assertEqual(current_info(d)['original_name'],'second.csv')
            newdata,_=read_source(current_info(d))
            self.assertAlmostEqual(float(newdata[(newdata.firma==AYGAZ)&(newdata.tarih.eq(pd.Timestamp('2026-01-15')))].fiyat.iloc[0]),52.70)


class TestRealPriceChart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df,_=ingest(sample(),'sample.csv')
        cls.brands=[PRIMARY,AYGAZ,IPRAGAZ]

    def test_only_true_price_changes(self):
        dates=change_dates(self.df,'KAYSERİ','Otogaz',self.brands)
        self.assertEqual([x.day for x in dates],[10,15,20])
        self.assertNotIn(pd.Timestamp('2026-01-05'),dates)

    def test_first_transition_is_visible(self):
        dates=change_dates(self.df,'KAYSERİ','Otogaz',self.brands)
        points,moves=movement_series(self.df,'KAYSERİ','Otogaz',self.brands,dates[0],dates[-1])
        self.assertIn(pd.Timestamp('2026-01-10'),set(moves['Tarih']))
        li=moves[moves['Firma kodu']==PRIMARY]
        self.assertAlmostEqual(float(li.iloc[0]['Önceki fiyat (TL)']),51)
        self.assertAlmostEqual(float(li.iloc[0]['Yeni fiyat (TL)']),52)
        self.assertTrue(points[(points.firma==PRIMARY)&points.tarih.eq(pd.Timestamp('2026-01-09'))].shape[0])
        self.assertTrue(points[(points.firma==PRIMARY)&points.tarih.eq(pd.Timestamp('2026-01-10'))].iloc[0]['is_event'])

    def test_price_step_shape_and_emphasis(self):
        dates=change_dates(self.df,'KAYSERİ','Otogaz',self.brands)
        points,_=movement_series(self.df,'KAYSERİ','Otogaz',self.brands,dates[0],dates[-1])
        fig=price_chart(points,self.brands,'KAYSERİ','Otogaz')
        self.assertEqual(len(fig.data),3)
        lk=next(x for x in fig.data if x.name=='Likitgaz')
        self.assertEqual(lk.line.shape,'hv')
        self.assertGreater(lk.line.width,4)
        self.assertTrue(all(v.line.width<lk.line.width for v in fig.data if v.name!='Likitgaz'))
        # Separate layout: same Likitgaz shown alongside each competitor.
        separate=price_chart(points,self.brands,'KAYSERİ','Otogaz',separate=True)
        self.assertEqual(len(separate.data),4)


if __name__=='__main__':
    unittest.main()
