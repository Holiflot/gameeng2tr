# OneOCR (Windows 11 Ekran Alıntısı Aracı OCR motoru) dosyalarını kopyalar.
# İsteğe bağlıdır: başarısız olursa uygulama Windows OCR veya RapidOCR kullanır.
$ErrorActionPreference = "Stop"
try {
    $pkg = Get-AppxPackage Microsoft.ScreenSketch | Sort-Object Version -Descending | Select-Object -First 1
    if (-not $pkg) { Write-Host "Ekran Alıntısı Aracı bulunamadı (OneOCR atlandı)."; exit 0 }
    $src = Join-Path $pkg.InstallLocation "SnippingTool"
    $dst = Join-Path $env:USERPROFILE ".config\oneocr"
    New-Item -ItemType Directory -Force $dst | Out-Null
    foreach ($f in "oneocr.dll", "oneocr.onemodel", "onnxruntime.dll") {
        Copy-Item (Join-Path $src $f) (Join-Path $dst $f) -Force
    }
    Write-Host "OneOCR hazır: $dst"
} catch {
    Write-Host "OneOCR kopyalanamadı ($($_.Exception.Message)). Sorun değil, diğer OCR motorları kullanılacak."
}
