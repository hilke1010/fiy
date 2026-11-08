@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Likitgaz V9 - Ortak Excel ve Fiyat Sıralamasi
ECHO.
ECHO LIKITGAZ Fiyat Analiz Platformu
ECHO ===============================
ECHO Bilgisayarinizin IPv4 adresi:
ipconfig | findstr /i "IPv4"
ECHO.
ECHO Bilgisayardan: http://localhost:8501
ECHO Telefondan: http://BILGISAYAR_IPV4:8501
ECHO fiyat.xlsx uygulamayla ayni klasorde ise otomatik okunur.
ECHO.
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
ECHO.
ECHO Program kapandi. Hata varsa yukaridaki metni inceleyin.
pause
