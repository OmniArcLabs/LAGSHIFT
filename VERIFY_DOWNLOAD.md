# Verify an official LAGSHIFT download

LAGSHIFT 1.0.0 is distributed without a paid Authenticode certificate. Windows
can therefore show `Unknown publisher` or a SmartScreen warning. This document
does not ask users to disable Windows security.

1. Download the installer only from the Releases section of
   `https://github.com/OmniArcLabs/LAGSHIFT`.
2. Open PowerShell in the download folder.
3. Run one of the following commands:

```powershell
Get-FileHash .\LAGSHIFT-1.0.0-Setup.exe -Algorithm SHA256
Get-FileHash .\LAGSHIFT-1.0.0-Setup-Light.exe -Algorithm SHA256
```

4. Compare the complete value, character for character, with
   [`SHA256SUMS.txt`](SHA256SUMS.txt) in the tagged source and release assets.
5. If the value differs, do not run the file. Delete it and report the download
   source through GitHub Issues. Do not publish diagnostic archives publicly.

SHA-256 confirms that the downloaded bytes match the published release file. It
does not replace Windows malware scanning, the official download source, or a
future trusted publisher signature.
