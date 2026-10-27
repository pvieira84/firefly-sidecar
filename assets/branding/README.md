# Firefly Sidecar application icon

Selected concept E, Reconciled: mint/blue reconciliation arrows, central checkmark
and amber accents on a navy rounded tile. Standalone artwork was created with
image generation from the approved comparison sheet, then its white outer corners
were made transparent with image generation. The 512px master is
`sidecar-reconciled.png`.

Run `python scripts/build_app_icons.py` (Pillow) to package the master into 16/32px
favicons, a multi-resolution ICO, 180px Apple touch icon, 192/512px PWA icons and a
padded opaque 512px maskable icon. Browser/PWA references use a version query to
refresh previous cached artwork. This does not change the Amazon extension icon.
