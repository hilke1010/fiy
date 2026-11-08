@echo off
chcp 65001 >nul
ECHO LIKITGAZ YEREL AG KONTROLU
ECHO =========================
ECHO 1) Bilgisayarin IPv4 adres(ler)i:
ipconfig | findstr /i "IPv4"
ECHO.
ECHO 2) 8501 portunda Streamlit calisiyor mu?
netstat -ano | findstr ":8501"
ECHO.
ECHO Cep telefonundan adres: http://IPV4_ADRESI:8501
ECHO Eger port DINLEMIYORSA once BASLAT.bat dosyasini acin.
ECHO Telefon baglanamiyorsa Windows Guvenlik Duvari / Ozel Ag (Private) TCP 8501 ayarlarini kontrol edin.
ECHO Sirkette misafir Wi-Fi veya cihaz izolasyonu (AP isolation) baglantiyi engelleyebilir.
ECHO.
pause
