# Heurísticas del Agente: Probabilidades y Sinergias Dinámicas

## 0. Conceptos Centrales
* **Visitas Esperadas:** Probabilidad de caer (simplificamos a distribución uniforme) * Número de Oponentes * Turnos estimados restantes.
* **EV_Propiedad:** Alquiler actual * Visitas Esperadas.
* **EV_Especiales:** Parking (Dinero acumulado * Probabilidad de caer) + Fantasy (Valor promedio neto de eventos * Probabilidad de caer).
* **Fondo:** Valor del alquiler más alto actualmente cobrable por cualquier rival en el tablero.
* **Reserva de seguridad:** Constante * Turno actual
* **Constante fantasía:** Constante que aproxima el valor medio de una casilla fantasía desconocida

## 1. Cárcel
* **EV_SalirCárcel:** (Propiedades libres / Propiedades totales) * CTE - (Propiedades ajenas / Propiedades totales)
* **EV_EstarEnCárcel:** - **EV_SalirCárcel**

## 2. Compra de Casillas y Movimientos Especiales
* **Propiedades:** EV = EV_Propiedad - Precio de compra 
* **Bridges y Servers:** Igual que propiedades
* **Trams:** Usar tranvía si EV_Destino > Coste del billete.

## 3. Elección de casilla
Se escoge la casilla con mayor valor esperado

## 4. Negocios y Construcción
* **Construir:** EV = (Aumento del alquiler * Visitas Esperadas) - Coste de construcción.
* **Demoler:** EV = Dinero recuperado - (Alquiler perdido * Visitas Esperadas).
* **Deshipotecar:** EV = (Alquiler recuperado * Visitas Esperadas) - Coste de deshipotecar (+ Bonus si reactiva monopolio).
* **Hipotecar:** EV = Dinero obtenido - (Alquiler perdido * Visitas Esperadas) (- Penalización masiva si desactiva monopolio).

## 5. Subastas
* **Puja Máxima Teórica:** EV_Propiedad (incluyendo sinergias y bloqueos).
* **Puja Real:** Mínimo entre Puja Máxima Teórica y (Dinero actual - Reserva de Seguridad).

## 6. Liquidación y Rendición
* **Liquidar:** Venta voraz (se venden primero las pripiedades menos valiosas)
* **Surrender:** Nunca

## 7. Intercambios
* **EV_Diferencial:** EV_Intercambio = Beneficio Neto Propio - (Beneficio Neto del Rival / Número de Oponentes Totales).
* **Proponer (Iniciativa):** Identificar propiedad deseada. Formular ofertas con EV_Intercambio global > 0, sin ceder ventajas críticas.
* **Sinergias y Bloqueos:** El EV del rival crece exponencialmente si la oferta le completa un color, volviendo el EV_Intercambio negativo (trato descartado).
* **Decisión:** Aceptar o proponer exclusivamente si EV_Intercambio > 0.

