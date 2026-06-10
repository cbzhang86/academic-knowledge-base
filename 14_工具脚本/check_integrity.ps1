$KnowledgeBase = "D:\公共管理科研"
$PdfDir = Join-Path $KnowledgeBase "01_论文原文"
$Md5Dir = Join-Path $KnowledgeBase "05_知识库索引\文件完整性"
$ok = 0; $missing = 0; $mismatch = 0

Get-ChildItem -Path $PdfDir -Recurse -Filter "*.pdf" | ForEach-Object {
    $pdfPath = $_.FullName
    $pdfName = $_.Name
    $md5File = Join-Path $Md5Dir "$pdfName.pdf.md5"
    $actualMd5 = (Get-FileHash -Path $pdfPath -Algorithm MD5).Hash.ToLower()
    
    if (-not (Test-Path $md5File)) {
        $missing++
        Write-Output "MISSING: $pdfName => $actualMd5"
    } else {
        $rawContent = (Get-Content $md5File -Raw).Trim()
        # 兼容旧格式 "HASH *filename" 提取纯哈希值
        if ($rawContent -match '^\s*([a-fA-F0-9]{32})') {
            $expectedMd5 = $Matches[1].ToLower()
        } else {
            $expectedMd5 = $rawContent.ToLower()
        }
        if ($expectedMd5 -ne $actualMd5) {
            $mismatch++
            Write-Output "MISMATCH: $pdfName"
        } else {
            $ok++
        }
    }
}

Write-Output "========================================"
Write-Output "OK: $ok  MISSING: $missing  MISMATCH: $mismatch"