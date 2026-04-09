# Fantasy events

::: magnate.models
    options:
      members:
        - FantasyEvent

::: magnate.fantasy
    options:
      members:
        - FantasyEventFactory.generate
        - FantasyEventFactory.apply_fantasy_event
