# Changelog

Los cambios se registran por revisión. Las entradas describen únicamente cambios implementados y comprobados.

## Unreleased

- Endurecido deploy/scripts/install-nginx.sh para instalar únicamente archivos ausentes o idénticos y abortar ante conflictos.
- Añadida reversión de los archivos y del enlace simbólico creados por el intento si falla nginx -t o la recarga.
- Eliminada la eliminación automática del sitio Nginx default; el instalador valida la configuración antes de recargar.
- Añadidas cinco pruebas aisladas con comandos simulados para éxito, conflictos, validación, activación y recarga.
- Actualizada la guía de instalación Nginx y sus pasos de verificación y recuperación.
- Añadido LICENSE con el texto oficial GNU GPL v3 y documentado el alcance GPL-3.0-only.
- Ampliado README.md con transferencia a servidor limpio, creación inicial y restablecimiento local de la contraseña administrativa.

- Preparada una copia de distribución sin historial Git ni configuración o datos operativos locales.
- Añadido manual de instalación limpia y cambio de contraseña; sanitizado el ejemplo de entorno.
- Añadido inventario de licencias y avisos de dependencias; consultar los pendientes de THIRD_PARTY_NOTICES.md.
