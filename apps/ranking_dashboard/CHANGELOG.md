# Changelog - Dashboard de Ranking Adaptativo

## [1.1.0] - 2025-10-25

### Agregado
- Animaciones de carga para operaciones de larga duración
- Spinner CSS animado con color primary (#023f66)
- Overlay semi-transparente durante procesamiento
- Mensajes contextuales según la operación

### Mejorado
- **Entrenar versión**: Muestra "Entrenando modelo... Esto puede tardar varios minutos."
- **Ciclo completo**: Muestra "Ejecutando ciclo completo: entrenar → evaluar → activar."
- **Evaluar versión**: Muestra "Evaluando versión X... Calculando métricas."
- **Activar versión**: Muestra "Activando versión..."
- **Rollback**: Muestra "Realizando rollback a versión anterior..."
- **Exportar datos**: Muestra "Exportando datos de entrenamiento..."

### Técnico
- CSS puro sin dependencias externas
- Animación `@keyframes spin` para el spinner
- JavaScript vanilla para activar/desactivar overlay
- Overlay con z-index 9999 para estar sobre todo el contenido

## [1.0.0] - 2025-10-25

### Inicial
- Dashboard web completo para gestión de ranking adaptativo
- Validación de usuario staff
- 6 páginas funcionales
- Integración con comandos de Django
- UI con Tailwind CSS
