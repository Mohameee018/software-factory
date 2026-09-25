$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force backups | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
docker run --rm -v factory_data:/source -v "${PWD}/backups:/backup" alpine:3.22 sh -c "tar -czf /backup/factory-data-$stamp.tar.gz -C /source ."
Write-Host "Created backups/factory-data-$stamp.tar.gz"
