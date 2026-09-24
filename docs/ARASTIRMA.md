# gameeng2tr — Araştırma Raporu

Hedef: Oyunlardaki İngilizce altyazıyı gerçek zamanlı olarak Türkçeye çevirip ekranda göstermek.

## 1. Altyazıyı yakalamanın üç yolu

| Yöntem | Nasıl çalışır | Artı | Eksi |
|---|---|---|---|
| **Ekran OCR** | Altyazı bölgesinin görüntüsü alınır, OCR ile metne çevrilir | Her oyunda çalışır, oyuna dokunmaz (anti-cheat riski yok) | OCR hataları, stilize fontlar, hareketli arka plan |
| **Ses (ASR)** | Sistem sesi (WASAPI loopback) Whisper vb. ile yazıya dökülür | Altyazısı olmayan oyunlarda da çalışır | GPU'yu oyunla paylaşır, müzik/efektle karışır, gecikme daha yüksek |
| **Metin kancalama (hook)** | Oyun motorunun metin fonksiyonları yakalanır | Kusursuz metin, OCR hatası yok | Motora özel (ör. Unity), online oyunlarda anti-cheat riski |

Sonuç: Ana yöntem **ekran OCR** olmalı; ses ve hook ileride eklenebilecek modüller.

## 2. İncelenen açık kaynak projeler

| Proje | Teknoloji | OCR | Çeviri | Türkçe | Lisans / Yıldız | Not |
|---|---|---|---|---|---|---|
| [Translumo](https://github.com/ramjke/Translumo) | C# / .NET 8 | Windows OCR, EasyOCR (ML ile en iyi sonucu seçer) | Google, DeepL, Yandex | Var | Apache-2.0, ~5.8k | En olgun proje. Çevrimdışı çeviri yok, tam ekran (exclusive) desteklemiyor |
| [RSTGameTranslation](https://github.com/thanhkeke97/RSTGameTranslation) | C# WPF + Python | OneOCR, Windows OCR | Google, Gemini, Groq, ChatGPT, Ollama, LM Studio | Belirtilmemiş | BSD benzeri, ~650 | Karakter adı algılama, TTS, STT |
| [LunaTranslator](https://github.com/HIllya51/LunaTranslator) | Python | Hook + dahili OCR | Çok sayıda, LLM, çevrimdışı | Yok | GPLv3, ~13k | Japonca görsel romanlara odaklı |
| [XUnity.AutoTranslator](https://github.com/bbepis/XUnity.AutoTranslator) | C# (BepInEx eklentisi) | — (hook) | Google, DeepL, özel HTTP, Ollama/OpenAI | Her dilden her dile | MIT, ~3.4k | Sadece Unity oyunları, çok kaliteli metin |
| [OCR-Translator (GCT)](https://github.com/tomkam1702/OCR-Translator) | Python / PySide6 | Gemini/Gemma/Qwen görsel modelleri | Gemini, DeepL | Belirtilmemiş | **Özel EULA** (açık kaynak değil) | "Find Subtitles" ile altyazı kutusunu otomatik bulma fikri iyi |
| [game-translator](https://github.com/951946538/game-translator) | Python | PaddleOCR | Ollama, LLM API, DeepL | — | — | Basit ve okunabilir referans mimari |
| [Real-Time-Translator](https://github.com/HaiHoang-AI/Real-Time-Translator) | Python / PySide6 | — (ses) | Ollama, Gemini, NLLB-200 (CTranslate2) | Hedef Vietnamca | MIT | WASAPI loopback + faster-whisper/Moonshine, tıklanamaz overlay |
| [interpreter](https://github.com/bquenin/interpreter) | Python | Yerel OCR | Çevrimdışı | — | — | Retro oyunlar, tamamen offline |

**Çıkarımlar**
- Hazır bir şey denemek istersen bugün **Translumo** + Google/DeepL ile İng→Tr çalışır.
- Hiçbiri **Türkçeye özel, çevrimdışı, bağlam farkındalıklı** bir çözüm sunmuyor. Bizim farkımız bu olabilir.

## 3. Bileşen seçenekleri

### Ekran yakalama
- [DXcam](https://github.com/ra1nty/DXcam) — Desktop Duplication, 1080p'de 240+ fps, tam ekran D3D uygulamalarında da stabil, WGC arka ucu da var.
- [wincam](https://github.com/lovettchris/wincam) — Windows Graphics Capture, <5 ms gecikme.
- Sadece altyazı bölgesi yakalanır, saniyede 5–10 kare yeterli.

### OCR (kaynak dil İngilizce olduğu için hepsi iyi durumda)
- **OneOCR** ([AuroraWright/oneocr](https://github.com/AuroraWright/oneocr)) — Windows 11 Ekran Alıntısı Aracı'nın OCR motoru; hızlı, CPU'da çalışır, kelime kutuları ve güven skoru döner. RSTGameTranslation bunu öneriyor.
- **Windows.Media.Ocr** — Windows 10/11 dahili, kurulum gerektirmez, yedek seçenek.
- **RapidOCR / PaddleOCR (ONNX)** — zor fontlar için; GPU'lu veya CPU'lu.

### Çeviri (İng→Tr)
| Seçenek | Tip | Hız | Kalite | Kaynak ihtiyacı |
|---|---|---|---|---|
| `Helsinki-NLP/opus-mt-tc-big-en-tr` + CTranslate2 INT8 | Offline NMT | CPU'da ~90 ms/cümle | İyi, bağlamsız | ~250 MB, GPU gerekmez |
| NLLB-200 distilled 600M/1.3B | Offline NMT | Orta | Orta–iyi | **CC-BY-NC** lisans |
| **TranslateGemma 4B / 12B** (Ocak 2026, Google) | Offline LLM (Ollama/llama.cpp) | 4B hızlı, 12B yavaş | Çok iyi, Türkçe destekli, bağlam alabilir | 4B Q4 ≈ 3 GB VRAM, 12B Q4 ≈ 8 GB VRAM |
| DeepL API (ücretsiz kota) | Online | ~200–400 ms | Çok iyi | İnternet + API anahtarı |
| Gemini Flash / diğer LLM API | Online | ~300–800 ms | Çok iyi + bağlam | İnternet + API anahtarı |

Not: Oyun GPU'yu yoğun kullanır. Yerel LLM ancak VRAM yeterliyse mantıklı; aksi halde CPU'da çalışan opus-mt oyunun FPS'ini etkilemeyen en güvenli seçenek.

### Overlay
- PySide6 çerçevesiz, her zaman üstte, şeffaf, **tıklanamaz** (`WS_EX_LAYERED | WS_EX_TRANSPARENT`) pencere.
- `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` ile overlay ekran yakalamaya girmez, böylece kendi çevirimizi tekrar OCR'lamayız ve altyazının üstüne doğrudan yazabiliriz.
- Oyun **pencereli tam ekran (borderless)** modda olmalı; exclusive fullscreen'de overlay görünmez.

## 4. Önerilen mimari

```
[Yakalama: DXcam/WGC, sadece altyazı bölgesi, 5–10 fps]
        │  kare farkı yoksa atla (hash / piksel farkı)
        ▼
[Ön işleme: büyütme, kontrast/eşikleme (dış hatlı altyazı fontları için)]
        ▼
[OCR: OneOCR → yedek Windows OCR / RapidOCR]
        │  metin 2 kare boyunca sabit mi? (daktilo efekti)
        │  bulanık karşılaştırma (rapidfuzz) ile son satırdan farklı mı?
        ▼
[Çeviri: önbellek (SQLite) → opus-mt (hızlı) | TranslateGemma | DeepL/Gemini]
        │  sözlük (karakter/yer isimleri), önceki 2–3 satır bağlam olarak
        ▼
[Overlay: tıklanamaz, yakalamadan hariç, kısayol tuşları]
```

Hedef gecikme (opus-mt ile): yakalama ~5 ms + OCR 20–60 ms + çeviri 30–150 ms → **~300 ms altı**.

### Önerilen teknoloji yığını
- Python 3.11+, PySide6 (arayüz + overlay), dxcam, oneocr, ctranslate2 + sentencepiece, rapidfuzz, keyboard/pynput (kısayollar), PyInstaller (tek exe).

### Aşamalı plan
1. **MVP:** Bölge seçimi → yakalama → OneOCR → opus-mt (CTranslate2) → overlay. Kısayollar: bölge seç, duraklat, gizle.
2. **Kararlılık:** Değişiklik algılama, stabil metin bekleme, bulanık tekrar engelleme, önbellek.
3. **Kalite:** TranslateGemma / DeepL / Gemini arka uçları, bağlam penceresi, oyun başına sözlük ve profil.
4. **Ekstralar:** Otomatik altyazı bölgesi bulma, ses (faster-whisper) modu, Unity oyunları için XUnity.AutoTranslator'a özel HTTP uç noktası sağlama.

## 5. Kararı etkileyecek bilgiler
- PC donanımı (özellikle GPU modeli ve VRAM, RAM, CPU, Windows sürümü)
- Tamamen çevrimdışı mı, yoksa DeepL/Gemini gibi online servisler kabul mü?
- Hangi oyunlar hedefleniyor (motor, tam ekran modu, online/anti-cheat)?
