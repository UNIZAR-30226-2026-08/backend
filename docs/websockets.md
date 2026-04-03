# WebSockets guide (placeholder)

**URL de Conexión:** `ws://backend.url/ws/game/{game_id}/`

## Mensajes del Cliente (Frontend -> Backend)
| Comando | Parámetros | Descripción |
| :--- | :--- | :--- |
| `roll_dice` | `{}` | Lanza los dados para el turno actual. |
| `buy_property` | `{"property_id": int}` | Compra la propiedad en la que está el jugador. |

## Mensajes del Servidor (Backend -> Frontend)
| Evento | Payload | Descripción |
| :--- | :--- | :--- |
| `player_moved` | `{"player": id, "position": int}` | Notifica que un jugador se ha movido. |
| `error_occurred` | `{"message": str}` | Notifica un error de lógica (ver sección de Excepciones). |
