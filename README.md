# gameeng2tr: Oyun Altyazı Çevirmeni (İngilizce → Türkçe)

Hikaye odaklı oyunlardaki (ör. Mortal Shell 2) İngilizce altyazıları ekrandan okuyup **gerçek zamanlı ve tamamen internetsiz** olarak Türkçeye çevirir. Çeviri, oyunun üstünde duran şeffaf ve tıklanamaz bir katmanda gösterilir.

İki çeviri motoru vardır. Uygulama içinden veya oyundayken kısayol tuşuyla aralarında geçiş yapabilirsiniz:

| Motor | Hız | Kalite | Kaynak kullanımı |
|---|---|---|---|
| **Opus-MT** (`Helsinki-NLP/opus-mt-tc-big-en-tr`, CTranslate2 INT8) | ~0,1 sn / altyazı | İyi | İşlemci, ~300 MB RAM. GPU'ya dokunmaz |
| **TranslateGemma 4B** (Google, Ollama üzerinden) | ~0,3–1 sn (GPU), 2–5 sn (CPU) | Daha doğal Türkçe | ~3,3 GB VRAM (veya sadece CPU modu) |

## Nasıl çalışır?

```
Ekran yakalama (DXGI, sadece altyazı bölgesi, 8 kare/sn)
   → Değişim algılama (sadece beyaz altyazı pikselleri değişince OCR)
   → OCR (OneOCR → Windows OCR → RapidOCR, hangisi varsa)
   → Altyazı takibi (harf harf yazılan altyazı bitene kadar bekler, titreşimleri eler)
   → Çeviri (önbellek + sözlük, konuşmacı adı korunur)
   → Overlay (en üstte, tıklanamaz, ekran yakalamadan hariç)
```

## Kurulum (Windows 10/11)

1. **Python 3.11 veya 3.12** kurun: <https://www.python.org/downloads/> ("Add python.exe to PATH" kutusunu işaretleyin).
2. TranslateGemma için **Ollama** kurun: <https://ollama.com/download> (veya `winget install Ollama.Ollama`).
3. Bu klasörde **`kurulum.bat`** dosyasını çalıştırın. Bir kez internet gerekir, sonrası tamamen çevrimdışıdır. Betik şunları yapar:
   - Sanal ortamı oluşturup paketleri kurar.
   - OneOCR dosyalarını Ekran Alıntısı Aracı'ndan kopyalamayı dener (isteğe bağlı).
   - Opus-MT modelini indirip CTranslate2 INT8 biçimine dönüştürür (~250 MB; dönüştürme için geçici olarak CPU sürümü PyTorch kurulur).
   - `ollama pull translategemma:4b` çalıştırır (~3,3 GB).
   - İki motoru da deneme cümlesiyle test eder.
4. **`baslat.bat`** ile uygulamayı açın.

Modelleri tek tek hazırlamak için:

```bat
venv\Scripts\python -m gameeng2tr.setup_models --opus
venv\Scripts\python -m gameeng2tr.setup_models --gemma
venv\Scripts\python -m gameeng2tr.setup_models --test
```

## Kullanım

1. Oyunu açın ve altyazıları etkinleştirin.
2. Uygulamada **Bölge seç** düğmesine basın (veya oyundayken `Ctrl+Alt+F12`), altyazının çıktığı alanı fareyle seçin. İki satırlık altyazılara yer bırakın. Varsayılan bölge ekranın alt ortasıdır ve çoğu oyunda doğrudan çalışır. Seçim ekranı oyunun o anki görüntüsünü gösterir. DirectX 11 exclusive fullscreen kullanan bir oyun seçim sırasında simge durumuna küçülebilir; seçimden sonra Alt+Tab ile oyuna dönün. Bölge bir kez seçilir ve kaydedilir.
3. **Başlat**'a basın (veya `Ctrl+Alt+F9`).

### Oyun içi kısayollar

| Kısayol | İşlev |
|---|---|
| `Ctrl+Alt+F9` | Çeviriyi başlat / durdur |
| `Ctrl+Alt+F10` | Motor değiştir (Opus-MT ⇄ TranslateGemma) |
| `Ctrl+Alt+F11` | Çeviriyi gizle / göster |
| `Ctrl+Alt+F12` | Altyazı bölgesini seç |

Kısayollar `%LOCALAPPDATA%\gameeng2tr\settings.json` dosyasından değiştirilebilir. `Ctrl+Alt+harf` kombinasyonları bilerek kullanılmadı: Türkçe Q klavyede bunlar AltGr ile aynıdır ve €, ₺ gibi karakterlerin yazılmasını engeller.

## Tam ekran oyunlar

- **Yakalama:** DXGI Desktop Duplication (DXcam) kullanılır. Bu yöntem tam ekran (exclusive fullscreen) DirectX oyunlarını da yakalar.
- **Overlay:** Unreal Engine 5 gibi DirectX 12 oyunlarında "Tam Ekran" modu aslında Windows'un flip-model sunumudur. Bu modda her zaman üstte duran pencereler görünür. Overlay her saniye kendini tekrar en üste taşır ve odak çalmaz, bu yüzden oyun simge durumuna küçülmez.
- DirectX 11 oyunlarında Windows 10/11'in **tam ekran iyileştirmeleri** açık kalmalıdır. `.exe` → Özellikler → Uyumluluk → "Tam ekran iyileştirmelerini devre dışı bırak" **işaretli olmamalıdır**.
- Buna rağmen çeviri görünmüyorsa oyunun ekran modunu **Kenarlıksız / Pencereli Tam Ekran** yapın. Performans farkı pratikte yoktur.
- Overlay **ekran yakalamadan hariç tutulur** (`WDA_EXCLUDEFROMCAPTURE`). Bu sayede çeviri İngilizce altyazının tam üstüne yazılsa bile OCR İngilizceyi okumaya devam eder. Bu özellik eski Windows sürümlerinde çalışmazsa çeviri otomatik olarak altyazının yukarısına taşınır.

## Performans ipuçları

- Mortal Shell 2 gibi Unreal Engine 5 oyunları çok VRAM kullanır. GPU'nuz **8 GB veya daha az VRAM**'e sahipse TranslateGemma için *Ayarlar → "Gemma'yı sadece CPU'da çalıştır"* seçeneğini deneyin ya da Opus-MT kullanın.
- Opus'a geçince Gemma varsayılan olarak VRAM'den çıkarılır. Geri geçiş birkaç saniye sürer. Hızlı geçiş istiyorsanız "Gemma'yı bellekte tut" seçeneğini açın.
- OCR sırası: **OneOCR** (en hızlı), **Windows OCR**, **RapidOCR** (en yavaş, her yerde çalışır).
- Windows OCR İngilizce dil paketi ister. Windows'unuz Türkçeyse yönetici PowerShell'de şunu çalıştırın:
  `Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"`
- Altyazı hareketli ve parlak bir arka plan üzerindeyse *Ayarlar → Yüksek kontrast* seçeneğini deneyin.

## Sözlük

*Ayarlar → Sözlüğü aç* ile `sozluk.json` dosyasını düzenleyebilirsiniz:

```json
{
  "kaynak": { "Foundiing": "Foundling" },
  "ceviri": { "Kabuk": "Shell" }
}
```

- `kaynak`: Çeviriden **önce** İngilizce metne uygulanır. Sık tekrarlanan OCR hatalarını düzeltmek için kullanılır.
- `ceviri`: Çeviriden **sonra** Türkçe metne uygulanır. Özel isimleri ve terimleri korumak için kullanılır.

Düzenledikten sonra *Sözlüğü yeniden yükle* düğmesine basın.

## Sorun giderme

- Log dosyası: `%LOCALAPPDATA%\gameeng2tr\gameeng2tr.log` (*Ayarlar → Veri klasörünü aç*).
- **"Opus-MT modeli bulunamadı"**: `venv\Scripts\python -m gameeng2tr.setup_models --opus` komutunu çalıştırın.
- **"Ollama'ya bağlanılamadı"**: Ollama'yı Başlat menüsünden açın. Uygulama `ollama serve` komutunu kendisi de başlatmayı dener.
- **Çeviri yanlış yerde:** *Ayarlar → Monitör* ile oyunun çalıştığı monitörü seçin ve bölgeyi yeniden seçin.

## Geliştirme

```bash
pip install -r requirements-dev.txt
pytest
```

Proje yapısı:

```
gameeng2tr/
  capture.py       ekran yakalama (DXcam / mss)
  preprocess.py    değişim algılama, kontrast
  ocr/             OneOCR, Windows OCR, RapidOCR
  textproc.py      OCR temizleme, altyazı takibi
  pipeline.py      yakalama → OCR → takip döngüsü
  translate/       opus.py, gemma.py, service.py (motor geçişi, önbellek), glossary.py
  ui/              overlay, bölge seçici, ana pencere
  controller.py    bileşenleri bağlar
  setup_models.py  model indirme / dönüştürme
```
