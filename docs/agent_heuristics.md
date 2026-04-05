# Heurísticas del Agente: Probabilidades y Sinergias Dinámicas

## 0. Conceptos Centrales
* **Visitas Esperadas:** Probabilidad de caer (basada en mapa de calor, no distribución uniforme) * Número de Oponentes * Turnos estimados restantes.
* **EV_Propiedad:** Alquiler actual * Visitas Esperadas.
* **EV_Especiales:** Parking (Dinero acumulado * Probabilidad de caer) + Fantasy (Valor promedio neto de eventos * Probabilidad).

## 1. Cárcel (Fórmula de Libertad Justa)
* **Ganancia Esperada al Moverse:** (Probabilidad de pasar por Salida * Dinero de Salida) + Suma de [MAX(0, EV_Propiedad - Precio de compra) * Probabilidad de caer] + EV_Especiales.
* **Pérdida Esperada al Moverse:** Suma de (Alquileres de casillas rivales * Probabilidad de caer en ellas).
* **EV_Libertad:** Ganancia Esperada al Moverse - Pérdida Esperada al Moverse.
* **Decisión:** Si EV_Libertad > 0, pagar fianza; si EV_Libertad <= 0, permanecer en la cárcel.

## 2. Reserva de Seguridad
* **Fondo:** Valor del alquiler más alto actualmente cobrable por cualquier rival en el tablero.

## 3. Compra de Casillas y Movimientos Especiales
* **Propiedades:** EV = EV_Propiedad - Precio de compra (+ Bonus por completar color propio o bloquear color rival).
* **Bridges y Servers:** Calcular EV proyectando el salto de alquiler exponencial según la cantidad en posesión.
* **Trams:** Usar tranvía si EV_Destino > Coste del billete.

## 4. Negocios y Construcción
* **Construir:** EV = (Aumento del alquiler * Visitas Esperadas) - Coste de construcción.
* **Demoler:** EV = Dinero recuperado - (Alquiler perdido * Visitas Esperadas).
* **Deshipotecar:** EV = (Alquiler recuperado * Visitas Esperadas) - Coste de deshipotecar (+ Bonus si reactiva monopolio).
* **Hipotecar:** EV = Dinero obtenido - (Alquiler perdido * Visitas Esperadas) (- Penalización masiva si desactiva monopolio).

## 5. Subastas
* **Puja Máxima Teórica:** EV_Propiedad (incluyendo sinergias y bloqueos).
* **Puja Real:** Mínimo entre Puja Máxima Teórica y (Dinero actual - Reserva de Seguridad).

## 6. Liquidación y Rendición
* **Liquidar:** Obligatorio demoler casas antes de hipotecar propiedades del mismo grupo. Comparar el EV de las opciones legales disponibles y ejecutar la acción que maximice el EV (mayor positivo o menor negativo).
* **Surrender:** Ejecutar si Deuda actual > Valor máximo de liquidación total (todo demolido e hipotecado).

## 7. Intercambios
* **EV_Diferencial:** EV_Intercambio = Beneficio Neto Propio - (Beneficio Neto del Rival / Número de Oponentes Totales).
* **Proponer (Iniciativa):** Identificar propiedad deseada. Formular ofertas con EV_Intercambio global > 0, sin ceder ventajas críticas.
* **Sinergias y Bloqueos:** El EV del rival crece exponencialmente si la oferta le completa un color, volviendo el EV_Intercambio negativo (trato descartado).
* **Decisión:** Aceptar o proponer exclusivamente si EV_Intercambio > 0.
