# Heurísticas del Agente: Probabilidades y Sinergias Dinámicas

## 0. Conceptos Centrales
* **Visitas Esperadas:** Probabilidad de caer (simplificamos a distribución uniforme) * Número de Oponentes * Turnos estimados restantes.
* **EV_Propiedad:** Alquiler actual * Visitas Esperadas.
* **EV_Especiales:** Parking (Dinero acumulado * Probabilidad de caer) + Fantasy (Valor promedio neto de eventos * Probabilidad de caer).

## 1. Cárcel (Fórmula de Libertad Justa)
* **Turno óptimo de salida:** Simplificamos la decisión de salir de la cárcel. En un
escenario ideal habría que valorar el estado del tablero (casillas por vender, valor
de los alquileres rivales, dinero de cada jugador...) para tomar la decisión de cuándo
salir. Observamos que en general a partir de cierto número de turnos de partida
casi siempre interesa permanecer en la cárcel para evitar grandes pérdidas.

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
