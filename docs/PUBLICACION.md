# Estado de preparación para publicación

## Preparado

- Copia independiente creada desde el working tree actual; no incluye historial Git.
- No incluye configuración real, bases de datos, certificados, llaves, respaldos, logs, PID, entornos virtuales ni node_modules.
- backend/.env.example usa marcadores reemplazables y valores locales genéricos.
- Recursos gráficos sin procedencia acreditada se excluyeron; no eran referenciados directamente por el código revisado.
- LICENSE contiene GNU GPL v3 y README declara GPL-3.0-only.
- THIRD_PARTY_NOTICES.md inventaría 237 paquetes frontend y 44 paquetes Python, con textos de licencia encontrados para las dependencias instaladas.
- El manual separa una instalación vacía de una migración y explica la creación inicial/restablecimiento del administrador.

## Confirmaciones del titular antes de publicar

- Confirmar quién es el titular legal del código propio y que está autorizado a licenciar las contribuciones bajo GPL-3.0-only. El historial por sí solo no acredita esa autorización.
- Sustituir OWNER/REPOSITORY por la URL real del repositorio público en el manual.
- Revisar el build que se publicará y conservar sus avisos. Los paquetes opcionales para plataformas distintas de Linux no se instalaron ni se incluyeron en el runtime Ubuntu; sus licencias están listadas en THIRD_PARTY_NOTICES.md.
- Decidir si se desean incorporar de nuevo los recursos gráficos excluidos, aportando su procedencia/licencia.
- Validar la instalación en una VM Ubuntu Server 24.04 limpia. No se ejecutó ninguna instalación ni suite de pruebas durante esta preparación.
- Revisar el historial del repositorio original antes de compartirlo. Esta carpeta no contiene ese historial; al publicarla, crea un repositorio nuevo desde esta copia limpia y no envíes la historia original.

## Nota sobre precio

La GPL trata las libertades de los usuarios, no el precio. El proyecto puede distribuirse gratuitamente; la GPL también permite que terceros redistribuyan copias con o sin cobro, sujeto a sus condiciones.
