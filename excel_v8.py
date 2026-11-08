# -*- coding: utf-8 -*-
"""V8 tek sayfalı, 3-katlı profesyonel Excel çıktı.
Güncel, önceki ve fark değişimi aynı ana matriste yan yana yazılır.
"""
from __future__ import annotations
import io
import pandas as pd
from advanced_engine import day_str


def export_matrix(matrix,when,prior_when=None):
    import xlsxwriter
    out=io.BytesIO()
    with xlsxwriter.Workbook(out,{'in_memory':True}) as wb:
        wb.set_properties({'title':'Likitgaz — İl/Ürün/Dağıtıcı Fiyat Farkı',
             'subject':'Likitgaz eksi rakip fiyatı — dönem karşılaştırması',
             'comments':'Fark = Likitgaz fiyatı - rakip fiyatı'})
        sh=wb.add_worksheet('Fiyat Farkı Matrisi')
        sh.hide_gridlines(2);sh.set_tab_color('#2563eb');sh.set_landscape();sh.fit_to_pages(1,0)
        sh.set_paper(9);sh.set_margins(.25,.25,.35,.35)
        title=wb.add_format({'font_size':20,'bold':True,'bg_color':'#092643','font_color':'#ffffff','valign':'vcenter'})
        info=wb.add_format({'font_size':10,'bg_color':'#e9f2fd','font_color':'#23405f','valign':'vcenter','text_wrap':True})
        groups=['#174e92','#12766c','#695193','#0d6c97','#815e41']
        grp=[wb.add_format({'bold':True,'font_color':'white','bg_color':c,'border':1,'border_color':'#99b0c9','align':'center','valign':'vcenter','font_size':12}) for c in groups]
        sub=wb.add_format({'bold':True,'font_color':'white','bg_color':'#1a3a5b','align':'center','valign':'vcenter','border':1,'border_color':'#88a7c7'})
        basehead=wb.add_format({'bold':True,'font_color':'white','bg_color':'#1e5ca7','align':'center','valign':'vcenter','border':1,'border_color':'#88a7c7'})
        phase=wb.add_format({'bold':True,'font_color':'#eff7ff','bg_color':'#1c456d','align':'center','valign':'vcenter','border':1,'border_color':'#88a7c7','text_wrap':True})
        phase_old=wb.add_format({'bold':True,'font_color':'#f4e1b6','bg_color':'#334a66','align':'center','valign':'vcenter','border':1,'border_color':'#88a7c7','text_wrap':True})
        phase_diff=wb.add_format({'bold':True,'font_color':'#ffe6a3','bg_color':'#655027','align':'center','valign':'vcenter','border':1,'border_color':'#88a7c7','text_wrap':True})
        rowcity1=wb.add_format({'bold':True,'bg_color':'#e7f0fd','font_color':'#1b426c','border':1,'border_color':'#c6d9ee'})
        rowcity2=wb.add_format({'bold':True,'bg_color':'#f5f9fe','font_color':'#1b426c','border':1,'border_color':'#c6d9ee'})
        moneyfmt='#,##0.00;[Red]-#,##0.00;0.00'
        signed='+0.00;-0.00;0.00'
        base=wb.add_format({'bold':True,'font_color':'#ffffff','bg_color':'#1e5ca7','num_format':moneyfmt,
                            'align':'center','border':1,'border_color':'#c6d9ee'})
        base_old=wb.add_format({'bold':True,'font_color':'#d2e5ff','bg_color':'#23466f','num_format':moneyfmt,
                            'align':'center','border':1,'border_color':'#c6d9ee'})
        regular=wb.add_format({'num_format':signed,'align':'center','border':1,'border_color':'#d7e3ef'})
        old=wb.add_format({'num_format':signed,'align':'center','font_color':'#334155',
                           'bg_color':'#f2f6fc','border':1,'border_color':'#d7e3ef'})
        diff=wb.add_format({'num_format':signed,'align':'center','font_color':'#6e4b12',
                           'bg_color':'#fff3d9','border':1,'border_color':'#d7e3ef','bold':True})
        neg=wb.add_format({'bg_color':'#ffe0e8','font_color':'#b91c43','bold':True})
        pos=wb.add_format({'bg_color':'#d1faed','font_color':'#067557','bold':True})
        eq=wb.add_format({'bg_color':'#edf2f7','font_color':'#566577'})
        count=len(matrix.columns)+1
        count=max(count,5)
        sh.merge_range(0,0,1,count-1,'LİKİTGAZ  /  TÜRKİYE DAĞITICI FİYAT FARKI MATRİSİ',title)
        sh.set_row(0,26);sh.set_row(1,21)
        prior_label=f'  •  Önceki karşılaştırma: {day_str(prior_when)}' if prior_when is not None else ''
        sh.merge_range(2,0,2,count-1,f'Güncel karşılaştırma: {day_str(when)}{prior_label}  •  Tüm tutarlar TL',info)
        sh.set_row(2,26)
        sh.merge_range(3,0,3,count-1,'Fark = LİKİTGAZ − RAKİP  |  Negatif / Kırmızı: Likitgaz daha düşük  |  Pozitif / Yeşil: Likitgaz daha yüksek  |  Mavi: Likitgaz fiyatı',info)
        sh.set_row(3,28)
        row_top=5
        row_company=6
        row_phase=7
        sh.merge_range(row_top,0,row_phase,0,'İL',grp[0]);sh.set_column(0,0,21)
        products=list(dict.fromkeys(matrix.columns.get_level_values(0)))
        col=1
        for pindex,product in enumerate(products):
            cols=[t for t in matrix.columns if t[0]==product]
            last=col+len(cols)-1
            if col==last:sh.write(row_top,col,product,grp[pindex%len(grp)])
            else:sh.merge_range(row_top,col,row_top,last,product,grp[pindex%len(grp)])
            j=col
            while j<=last:
                firm=matrix.columns[j-1][1]
                k=j
                while k+1<=last and matrix.columns[k][1]==firm:k+=1
                if k==j:sh.write(row_company,j,firm,basehead if firm=='Likitgaz' else sub)
                else:sh.merge_range(row_company,j,row_company,k,firm,basehead if firm=='Likitgaz' else sub)
                j=k+1
            for idx in range(col,last+1):
                fuel,firm,view=matrix.columns[idx-1]
                format_=phase_diff if view=='Fark değişimi' else phase_old if view.startswith('Önceki') else phase
                sh.write(row_phase,idx,view,format_)
                sh.set_column(idx,idx,16.5 if 'fiyat' in view else 15)
            col=last+1
        for r in [row_top,row_company,row_phase]:sh.set_row(r,27)
        for i,(city,series) in enumerate(matrix.iterrows()):
            row=row_phase+1+i
            sh.set_row(row,22)
            sh.write(row,0,str(city),rowcity1 if i%2==0 else rowcity2)
            for j,(key,value) in enumerate(series.items(),start=1):
                product,firm,view=key
                f=(base_old if view=='Önceki fiyat' else base) if firm=='Likitgaz' else (diff if view=='Fark değişimi' else old if view=='Önceki fark' else regular)
                if pd.isna(value):sh.write_blank(row,j,None,f)
                elif view=='Fark değişimi':
                    # Delta her zaman önceki ve güncel yan yana bulunduğu zaman formüldür.
                    prior_col=j-1;present_col=j-2
                    # 0 tabanlı indisleri Excel sütunlarına çevir.
                    cell_present=xlsxwriter.utility.xl_rowcol_to_cell(row,present_col)
                    cell_prior=xlsxwriter.utility.xl_rowcol_to_cell(row,prior_col)
                    sh.write_formula(row,j,f'={cell_present}-{cell_prior}',f,float(value))
                else:sh.write_number(row,j,float(value),f)
        if len(matrix):
            last=row_phase+len(matrix)
            for j,(_p,_firm,view) in enumerate(matrix.columns,start=1):
                if view not in ('Güncel fark','Önceki fark'):continue
                sh.conditional_format(row_phase+1,j,last,j,{'type':'cell','criteria':'<','value':0,'format':neg})
                sh.conditional_format(row_phase+1,j,last,j,{'type':'cell','criteria':'>','value':0,'format':pos})
                sh.conditional_format(row_phase+1,j,last,j,{'type':'cell','criteria':'==','value':0,'format':eq})
        sh.freeze_panes(row_phase+1,1)
        footer=row_phase+len(matrix)+3
        sh.merge_range(footer,0,footer,count-1,
            'Dönem fiyatı: o güne kadar yürürlüğe giren son kayıt.  Fark değişimi = Güncel fark − Önceki fark.  Verisi olmayan hücreler boş bırakılır.',info)
        sh.set_row(footer,28)
        sh.print_area(0,0,footer,count-1)
        sh.set_header('&C&B LİKİTGAZ · FİYAT İSTİHBARATI')
        sh.set_footer('&L İç rapor &C &P / &N &R '+day_str(when))
    out.seek(0)
    return out.getvalue()
