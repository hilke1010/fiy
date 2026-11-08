# Likitgaz Fiyat Analiz Platformu – V9 / Fiyat Sıralaması ve Ortak Excel

Bu sürüm, kullanıcının yüklediği **V9 tabanlı** uygulamanın devamıdır. Mevcut Türkiye haritası, çok ürünlü fiyat farkı matrisi, XLSX dışa aktarma ve yönetici analizi korunur. Yeni bölüm **Likitgaz'ın seçilen rakibe göre önce yüksekken sonra düşük kalması (ve tersi)** olaylarını açıkça gösterir.

## 1. Klasörden otomatik güncel Excel (önerilen yöntem)

Uygulama dosyaları ile aynı klasörde şu dosyayı bulundurun:

```
Likitgaz_Uygulama/
  app.py
  engine.py
  ...
  fiyat.xlsx      <-- 150.000 satırlık gerçek dosyanız
```

- Uygulama `fiyat.xlsx` dosyasını **otomatik** okur. Tek tek telefonlardan dosya yüklenmez.
- Excel'i güncelleyip **kaydettiğinizde** tüm açık oturumlar yaklaşık 15 saniyelik aralıklarla dosyanın sürüm değişikliğini fark eder; yeni bağlantılar doğrudan aynı ortak dosyayı görür.
- Excel'i kopyalarken/kaydederken işlemin tamamen bitmesini bekleyin. Uygulama dosya yazılırken kısa süreli okuma hatası verebilir; tamamlandığında yeniden okunur.
- Desteklenen otomatik adlar: `fiyat.xlsx`, `fiyat.xls`, `fiyat.csv` (öncelik bu sıradadır).
- Dosya program sunucusu olan **bilgisayarda** bulunmalıdır; telefonda değil.
- Alternatif: Soldaki **Yönetici: Yeni Excel yayımla** alanına yönetici PIN'iyle (`1969`, ortam değişkeni `LIKITGAZ_UPLOAD_PIN` ile değiştirilebilir) girip Excel yükleyerek ortak dosyayı yayımlayın. En son kaydedilen kaynak kullanılır. Klasördeki `fiyat.xlsx` dosyasını tekrar kaydederseniz tekrar aktif olur.
- **Güncel**, otomatik internetten akaryakıt fiyatı çekildiği anlamına gelmez; en son kaydedilen/yayımlanan Excel demektir.

Güvenlik: Siteye bağlanan ağ kullanıcıları raporları görebilir. Excel'i arayüz üzerinden yükleyerek değiştirmek için yönetici PIN'i gerekir; ancak `fiyat.xlsx` dosyasına işletim sisteminden yazma izni olanlar doğrudan güncelleyebilir. Bu çözüm internete açık sunucu kimlik doğrulaması yerine geçmez.

## 2. Uygulamayı çalıştırma

Klasörde PowerShell açın:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Alternatif `BASLAT.bat` dosyasına çift tıklayın. Bilgisayarınızın IPv4 adresini de listeler.

- Bilgisayarda: `http://localhost:8501`
- Telefonda: `http://BILGISAYARIN_IPV4_ADRESI:8501` (örnek: `http://192.168.1.105:8501`)
- Telefon ve bilgisayar aynı yerel ağa bağlı olmalı. `localhost` **telefonda** bilgisayarı göstermez.
- Bilgisayarda **eski V9/V11 çalışıyorsa** önce o PowerShell oturumunu `Ctrl+C` ile kapatın; 8501 portunu tek program kullanabilir.

### Aynı ağda telefondan hiç açılmıyorsa

1. Bilgisayarda `AG_KONTROL.bat` açın; IPv4 adresini ve TCP 8501 portunun dinlenip dinlenmediğini görün.
2. Bilgisayardan kendi IPv4 adresiyle de deneyin: `http://192.168.x.x:8501`.
3. Windows ağ profiliniz **Özel (Private)** ise, yönetici olarak PowerShell'de yalnız Özel ağ için aşağıdaki kuralı ekleyebilirsiniz:

```powershell
New-NetFirewallRule -DisplayName "Likitgaz Streamlit 8501 (Private)" -Direction Inbound -Protocol TCP -LocalPort 8501 -Action Allow -Profile Private
```

Bu kural Yönetici yetkisi ister. Şirket ağlarında izin almadan ağ kuralı değiştirmeyin. Misafir Wi-Fi, VPN veya kablosuz **client isolation / AP isolation** varsa cihazlar birbirine ulaşamayabilir; bunu Streamlit kodu çözemez.

### Yavaş açılıyorsa

- 150.000 satırlık `.xlsx` ilk okunuşta zaman alabilir. Uygulama temizlenmiş veriyi ve harita hazırlığını önbellekler; sonraki ziyaretçilerde Excel baştan okunmak zorunda değildir.
- İlk Türkiye haritası açılışında il sınırları/harita döşemeleri internetten yüklenebilir. Elinizde varsa `turkiye_iller.geojson` dosyasını uygulama klasörüne koyun; sınırların indirilmesi gerekmez.
- Uygulama OneDrive benzeri eşitlemeli klasördeyse açılış yavaşlayabilir; veriyi ve kodu yerel bir klasörde (örn. `C:\\LikitgazDashboard`) çalıştırmayı deneyin.
- Tüm değişkenleri daha hızlı görüntülemek için başlangıçta yalnız iki rakip seçin.

## 3. Yeni grafik: sıralama değişimleri

Birinci sekme **Türkiye Fiyat Haritası** altındaki yeni bölüm: **Likitgaz / Rakip Fiyat Sıralaması · Dönemsel Geçişler**.

- İl, ürün, Aygaz/İpragaz vb. rakipleri seçin.
- Varsayılan kapsam **Likitgaz geçişleri**: Likitgaz'ın gerçek fiyat değiştiği tarihlerde, aynı gün yürürlükte olan rakip fiyatı ile karşılaştırma.
- Alternatif **Seçilen tüm şirketlerin geçişleri**: Rakibin tek başına zam veya indirim yaptığı günleri de tarar.
- Yalnızca **gerçek fiyat değişim tarihleri** seçilir. Fiyatın tekrar aynı tutarla kaydedilmesi zam sayılmaz.
- Her rakip için ayrı bir çizgi paneli oluşturulur; **sarı kesik sıfır çizgisi** karşılaştırmanın yönünü gösterir:
  - **Negatif/kırmızı:** Likitgaz fiyatı rakibin altında.
  - **Pozitif/yeşil:** Likitgaz fiyatı rakibin üstünde.
  - **Altın yıldız:** iki şirketin fiyat sıralaması değişti (doğrudan pozitiften negatife ya da tersi).
- Geçiş notlarında iki tarihteki **Likitgaz fiyatı, rakip fiyatı, fark, fark değişimi, iki fiyatın ayrı hareketi** ve yön açıkça yazılır. İyi/kötü, lehine/aleyhine değerlendirmesi yapılmaz.
- Alttaki seçenekle önceki **TL fiyat basamakları grafiği** de açılabilir.

**Hesap:** `Fark = Likitgaz fiyatı − rakip fiyatı`. Örneğin `+0,20 TL → −0,30 TL`, fiyat sıralaması değişmiştir; fark değişimi `−0,50 TL`'dir.

## 4. Değişmeyen V9 işlevleri

- Türkiye fiyat haritası, il tıklamaları ve önceki dönem farkları.
- Çok ürünlü tek fiyat farkı matrisi, istenirse önceki dönem sütunları, profesyonel Excel `.xlsx` aktarımı.
- Yönetici makine analizi.
- Firma/ürün/il adlarında Türkçe karakter desteği.

## 5. Test ve bakım

```powershell
python -m unittest test_shared_chart test_rank_and_local -v
```

On bir otomatik testte geçiş hesapları, yerel `fiyat.xlsx` değişikliklerinin algılanması ve eski V9 grafiği doğrulandı. Canlı Windows/telefon tarayıcı testi ve sizin 150.000 satırlık Excel'inizle son kontrol henüz yapılmadı.

`.streamlit/config.toml` dosyası yerel ağda `0.0.0.0:8501` üzerinde dinlemek üzere ayarlanmıştır. Kod dosyalarını değiştirdikten sonra yeniden başlatmak gerekebilir; `fiyat.xlsx` için yeniden başlatmaya gerek yoktur.


## 08.11.2026 - Excel doğrulama düzeltmesi

`fiyat.xlsx` aynı uygulama klasöründeyken yanlışlıkla SHA-256 bütünlük hatası oluşturulması düzeltildi. `app.py` kaynak kipini artık önbellek fonksiyonuna aktarır. `shared_store.py`, yerel sürüm kimliği ile yayımlanan dosyanın SHA-256 doğrulamasını ayrı işler. Mevcut Excel değiştirilmez.
