# Third-party notices

The Windows package includes a Python runtime, PySide6/Qt and Shiboken, the OpenAI
Python SDK, and their bundled dependencies. They retain their respective licenses;
this document does not grant a project-wide ChibiMate license.

## Included notices and sources

- Python: `_internal/licenses/python/LICENSE.txt`;
  [CPython source](https://github.com/python/cpython).
- PySide6/Qt and Shiboken 6.12.0: installed metadata under `_internal/*.dist-info`,
  plus unmodified LGPLv3, GPLv2 and GPLv3 texts under `licenses/qt/`, obtained from
  the [Qt for Python v6.12.0 LICENSES directory](https://github.com/qtproject/pyside-pyside-setup/tree/v6.12.0/LICENSES).
  Sources: [Qt for Python](https://code.qt.io/cgit/pyside/pyside-setup.git/)
  and [Qt](https://code.qt.io/cgit/qt/).
- OpenAI Python SDK: `_internal/openai-*.dist-info/licenses/LICENSE`;
  [upstream source](https://github.com/openai/openai-python).
- Other Python dependency notices remain in `_internal/*dist-info/`. Metadata
  records versions and upstream links. `certifi/cacert.pem` is a public certificate
  authority bundle, not a private API credential.
- PyInstaller's bootloader distribution exception is described in its
  [upstream license](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt).

## Publication review still required

Installed PySide6/Shiboken metadata declares open-source license alternatives, but
its license directories supplied only a commercial-license notice. The open-source
texts above supplement those files; the commercial notice is not evidence that
this project holds a commercial license.

Review the applicable Qt/module and bundled third-party terms, including how to
provide corresponding library sources, before distributing publicly. Upstream links
and copied texts alone are not a claim that all obligations are fulfilled. See
[Qt licensing](https://doc.qt.io/qt-6/licensing.html) and
[Qt's LGPL guidance](https://www.qt.io/development/open-source-lgpl-obligations).

No project software license has been selected. No rights to third-party character
artwork are granted here. The Windows ZIP excludes the repository's Alya images,
sprite sheet, exported animation pack, and all user-imported/generated data.
