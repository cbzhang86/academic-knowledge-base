# Paper Workflow 备份脚本
# 用途：压缩知识库 .md 文件 + 备份 PDF 原文到 99_备份/ 目录
# 用法：powershell -File backup.ps1

$KnowledgeBase = "D:\公共管理科研"
$BackupDir = Join-Path $KnowledgeBase "99_备份"
$Timestamp = Get-Date -Format 'yyyyMMdd_HHmm'

# 确保备份目录存在
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

# ========================================
# 1. 增量备份：压缩 .md 文件
# ========================================
$MdBackup = Join-Path $BackupDir "backup_md_$Timestamp.zip"
Compress-Archive -Path "$KnowledgeBase\*.md", "$KnowledgeBase\*\*\*.md" -DestinationPath $MdBackup -Force
Write-Output "[MD] 备份完成: $MdBackup"

# ========================================
# 2. PDF 原文备份：复制 01_论文原文\ 下所有 .pdf 保持子目录结构
# ========================================
$PdfBackupRoot = Join-Path $BackupDir "论文原文备份"
$PdfSourceDir = Join-Path $KnowledgeBase "01_论文原文"

if (Test-Path $PdfSourceDir) {
    Get-ChildItem -Path $PdfSourceDir -Recurse -Filter "*.pdf" | ForEach-Object {
        $relativePath = $_.FullName.Substring($PdfSourceDir.Length + 1)
        $destPath = Join-Path $PdfBackupRoot $relativePath
        $destDir = Split-Path $destPath -Parent
        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        }
        Copy-Item -Path $_.FullName -Destination $destPath -Force
    }
    Write-Output "[PDF] 备份完成: $PdfBackupRoot"
} else {
    Write-Output "[PDF] 源目录不存在，跳过 PDF 备份"
}

# ========================================
# 3. 清理 7 天前的旧备份
# ========================================
Get-ChildItem -Path $BackupDir -Filter "backup_md_*.zip" | 
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
    Remove-Item -Force

Write-Output "已清理 7 天前的旧备份"