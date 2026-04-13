from django.db import models
from django.contrib.auth.models import AbstractUser
from polymorphic.models import PolymorphicModel

class CustomUser(AbstractUser):
    """
    Extended user model for the Magnate game platform.

    Inherits from Django's AbstractUser and adds game-specific profile data,
    matchmaking state, and progression metrics.

    Attributes:
        username (CharField): Unique display name, max 40 characters.
        current_private_room (ForeignKey -> PrivateRoom | None): The private room
            the user is currently in, if any. When set, `ready_to_play` is interpreted
            as the player's ready status within that room. When null, `ready_to_play`
            signals the user is searching for a public game.
        ready_to_play (BooleanField): Dual-purpose flag. Inside a private room: whether
            the player has marked themselves ready. Outside a room: whether the player
            is actively queued for a public matchmaking game.
        role (CharField): Access level of the user. One of ``Roles.regular`` or
            ``Roles.admin``.
        owned_items (ManyToManyField -> Item): Cosmetic or gameplay items the user
            has purchased or unlocked.
        played_games (ManyToManyField -> Game): All games the user has participated in,
            linked through ``PlayerGameStatistic`` for per-game stats.
        active_game (ForeignKey -> Game | None): The game session the user is currently
            playing in, if any.
        points (PositiveIntegerField): Accumulated platform points (currency for the shop).
        exp (PositiveIntegerField): Experience points used for progression/leveling.
        elo (PositiveIntegerField): Matchmaking rating reflecting competitive skill.
        user_piece (PositiveIntegerField): ID of the board piece the user has selected.
        num_played_games (PositiveIntegerField): Lifetime count of completed games.
        num_won_games (PositiveIntegerField): Lifetime count of games won.
    """
    username = models.CharField(max_length=40, unique=True)
    current_private_room: "PrivateRoom | None" = models.ForeignKey( 'PrivateRoom', on_delete=models.SET_NULL,  null=True,  blank=True,related_name='players') # type: ignore
    ready_to_play = models.BooleanField(default=False) # depending of the current private room could be interpreted as  ready or looking for a public game


    class Roles(models.TextChoices):
        regular = 'regular'
        admin = 'admin'
    role = models.CharField(choices=Roles, max_length=10, default='regular')

    owned_items = models.ManyToManyField('Item', blank=True, related_name='owners')
    played_games = models.ManyToManyField(
        'Game', 
        through='PlayerGameStatistic', 
        blank=True, 
        related_name='played_by'
    )

    active_game: "Game | None" = models.ForeignKey('Game', 
                                    on_delete=models.SET_NULL,
                                    null=True,
                                    blank=True,
                                    related_name='active_players') # type: ignore
    

    # Big ?
    points = models.PositiveIntegerField(default=0)
    exp = models.PositiveIntegerField(default=0)
    elo = models.PositiveIntegerField(default=0)
    user_piece = models.PositiveIntegerField(default=1) #TODO: poner default cuando tengamos fichas definidas
    num_played_games = models.PositiveIntegerField(default=0) #TODO: ir aumentando este dato
    num_won_games = models.PositiveIntegerField(default=0) #TODO: ir aumentando este dato
    

class Bot(CustomUser):
    """
    A computer-controlled player that participates in games alongside human users.

    Inherits all fields from ``CustomUser`` and adds bot-specific configuration.

    Attributes:
        bot_level (CharField | None): Difficulty setting for the bot's decision-making,
            e.g. ``"easy"``, ``"medium"``, or ``"expert"``. Null if not configured.
        has_proposed_trade (BooleanField): Whether the bot has already initiated a trade
            proposal in the current turn, used to prevent multiple simultaneous proposals.
    """
    bot_level = models.CharField(max_length=20, null=True, blank=True) # "easy" /"expert" etc
    has_proposed_trade = models.BooleanField(default=False)


class Item(models.Model):
    """
    A purchasable cosmetic item available in the in-game shop.

    Items can be board pieces or emojis and are bought with the user's ``points``.

    Attributes:
        custom_id (PositiveIntegerField): Unique game-level identifier for the item,
            separate from the database primary key.
        itemType (CharField): Category of the item. One of ``ItemType.piece`` (a board
            token) or ``ItemType.emoji`` (a chat/reaction emoji).
        price (PositiveIntegerField): Cost in platform ``points`` to purchase the item.
    """
    class ItemType(models.TextChoices):
        piece = 'piece'
        emoji = 'emoji'
    custom_id = models.PositiveIntegerField(unique=True)
    itemType = models.CharField(choices=ItemType, max_length=10, default='ficha')
    price = models.PositiveIntegerField(default=0)


###############################################################################

class Board(models.Model):
    """
    Represents the physical game board for a Magnate session.

    A Board groups all ``BaseSquare`` instances that belong to a specific board
    layout. Different boards can represent different map configurations.

    Attributes:
        custom_id (PositiveIntegerField): Game-level identifier for the board layout.
    """
    # active_fantasy_cards = ...
    custom_id = models.PositiveIntegerField(default=0)
    pass

class BaseSquare(PolymorphicModel):
    """
    Abstract polymorphic base class for all squares on the game board.

    Uses ``django-polymorphic`` so that queries on ``BaseSquare`` transparently
    return the concrete subclass instance (e.g. ``PropertySquare``, ``JailSquare``).

    Attributes:
        custom_id (PositiveIntegerField): Game-level identifier used in game state
            JSON fields (e.g. ``Game.positions``).
        board (ForeignKey -> Board | None): The board layout this square belongs to.
        in_successor (ForeignKey -> BaseSquare | None): The next square when entering
            this square via the main path (standard movement direction). The reverse
            relation ``in_predecessors`` gives all squares that lead into this one
            on the main path.
    """
    custom_id = models.PositiveIntegerField(default=0)
    board = models.ForeignKey('Board',
                              on_delete=models.SET_NULL,
                              null=True,
                              blank=True,
                              related_name='part_of_table')
    in_successor = models.ForeignKey('BaseSquare',
                              on_delete=models.SET_NULL,
                              null=True,
                              blank=True,
                              related_name='in_predecessors')

class PropertySquare(BaseSquare):
    """
    A purchasable street property on the board.

    Groups of ``PropertySquare`` instances sharing the same ``group`` value form
    a colour set; owning the full set unlocks house building.

    Attributes:
        group (PositiveIntegerField): Colour group identifier. All squares with the
            same value form a monopoly set.
        buy_price (PositiveIntegerField): Cost to purchase the property from the bank.
        build_price (PositiveIntegerField): Cost per house (or hotel) to build on the
            property once the full colour set is owned.
        rent_prices (JSONField): Array of 6 integers representing rent charged to a
            landing player: ``[base, full_set, 1_house, 2_houses, 3_houses, hotel]``.
    """
    # Change
    group = models.PositiveIntegerField(default=0)
    buy_price = models.PositiveIntegerField(default=0)
    build_price = models.PositiveIntegerField(default=0)
    # An int[6] array
    rent_prices = models.JSONField(null=True)

class FantasySquare(BaseSquare):
    """
    A square that triggers a random ``FantasyEvent`` when landed on.

    Equivalent to Chance / Community Chest squares in classic Monopoly. No extra
    data beyond the inherited ``BaseSquare`` fields is needed; the event itself is
    stored in ``FantasyEvent``.
    """
    pass

class BridgeSquare(BaseSquare):
    """
    A purchasable bridge (transport link) square.

    Bridges have two exit paths: the standard ``in_successor`` (main board path)
    and an ``out_successor`` (the shortcut route taken when travelling via the
    bridge). Rent scales depending on how many bridges the same owner controls.

    Attributes:
        buy_price (PositiveIntegerField): Cost to purchase the bridge from the bank.
        rent_prices (JSONField): Array of rent values indexed by the number of bridges
            owned by the same player.
        out_successor (ForeignKey -> BaseSquare | None): The square a player arrives at
            when using this bridge as a shortcut. The reverse relation ``out_predecessors``
            identifies all bridge squares that route here.
    """
    buy_price = models.PositiveIntegerField(default=0)
    rent_prices = models.JSONField(null=True)
    out_successor = models.ForeignKey('BaseSquare',
                              on_delete=models.SET_NULL,
                              null=True,
                              blank=True,
                              related_name='out_predecessors')

class TramSquare(BaseSquare):
    """
    A purchasable tram/metro station square.

    Landing on an owned tram station may give the landing player an optional detour
    via the tram network. The ``choose_square`` game phase is triggered when a player
    can board a tram.

    Attributes:
        buy_price (PositiveIntegerField): Cost to purchase the tram station from the bank.
    """
    buy_price = models.PositiveIntegerField(default=0)

class ParkingSquare(BaseSquare):
    """
    A "Free Parking" style square that accumulates a money jackpot.

    Fines and fees paid during the game are added to ``money``; the player who
    lands on this square collects the full pot.

    Attributes:
        money (PositiveIntegerField): Current jackpot amount held by this square.
            Mirrored by ``Game.parking_money`` for active game state tracking.
    """
    money = models.PositiveIntegerField(default=0)

class ServerSquare(BaseSquare):
    """
    A purchasable utility square (server/internet infrastructure theme).

    Rent is calculated as a multiple of the dice roll, making it variable. Two
    rent tiers exist depending on whether the owner controls one or both server squares.

    Attributes:
        buy_price (PositiveIntegerField): Cost to purchase the utility from the bank.
        rent_prices (JSONField): Array of 2 integers: ``[one_owned_multiplier,
            both_owned_multiplier]`` applied to the dice roll total.
    """
    buy_price = models.PositiveIntegerField(default=0)
    # An int[2] array
    rent_prices = models.JSONField(null=True)

class ExitSquare(BaseSquare):
    """
    The starting "GO" square of the board.

    Players collect ``init_money`` each time they pass over or land on this square.

    Attributes:
        init_money (PositiveIntegerField): The salary/bonus amount awarded to a player
            upon passing this square.
    """
    init_money = models.PositiveIntegerField(default=0)

class GoToJailSquare(BaseSquare):
    """
    A square that immediately sends the landing player to jail.

    No additional data is required; the game logic handles the teleport and
    jail state update when a player lands here.
    """
    pass

class JailSquare(BaseSquare):
    """
    The jail square where imprisoned players serve their sentence.

    Players are moved here by ``GoToJailSquare`` or certain ``FantasyEvent`` types.
    They can leave by rolling doubles, paying ``bail_price``, or waiting out their
    remaining turns (tracked in ``Game.jail_remaining_turns``).

    Attributes:
        bail_price (PositiveIntegerField): The fixed fee a player can pay via
            ``ActionPayBail`` to be released from jail immediately.
    """
    bail_price = models.PositiveIntegerField(default=0)

class JailVisitSquare(BaseSquare):
    """
    The "Just Visiting" portion of the jail square.

    Players who land here through normal movement are not imprisoned; they are
    merely visiting. No extra data is needed beyond the inherited ``BaseSquare`` fields.
    """
    pass

###############################################################################

#------ Models for Public Matchmaking Queue ------#
class PublicQueuePosition(models.Model):
    """
    Represents a single user's position in the public matchmaking queue.

    Entries are created when a user sets ``ready_to_play = True`` outside of any
    private room. The matchmaking service polls this table to group players into
    games.

    Attributes:
        user (ForeignKey -> CustomUser): The user waiting in the queue.
        channel (CharField): The WebSocket channel name used to push matchmaking
            updates back to this specific user.
        date_time (DateTimeField): Timestamp of when the user joined the queue,
            used for fair ordering.
    """
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    channel = models.CharField(max_length=300) 
    date_time = models.DateTimeField()

#------ Models for Private Management ------#
class PrivateRoom(models.Model):
    """
    A lobby where a group of players assemble before starting a private game.

    The room owner configures the game settings and triggers game creation once
    everyone is ready. Human players are linked via ``CustomUser.current_private_room``;
    bots are added automatically to fill any remaining slots up to ``target_players``.

    Attributes:
        owner (ForeignKey -> CustomUser): The user who created the room. They have
            administrative control (kicking players, starting the game).
        room_code (CharField): A short, unique code that other players enter to join
            this room.
        players (QuerySet[CustomUser]): Reverse relation from ``CustomUser.current_private_room``;
            all users currently in this room.
        target_players (PositiveIntegerField): Total number of seats in the game
            (human + bot). Bots are added to fill the gap between real players and
            this target when the game starts.
        bot_level (CharField): Default difficulty for any bots added to this room,
            e.g. ``"easy"``, ``"medium"``, or ``"hard"``.
    """
    #The one who starts the room and later the game
    owner:"CustomUser | None" = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='hosted_rooms')# type: ignore
    # Players will be linked from CustomUser.current_private_room
    room_code: str = models.CharField(max_length=10, unique=True) #type: ignore
    players: models.QuerySet['CustomUser']
    # Number of players total -> to include bots
    target_players = models.PositiveIntegerField(default=4)
    bot_level = models.CharField(max_length=20, default='medium')
    
class FantasyEvent(models.Model):
    """
    A Chance/Community-Chest style event card drawn when a player lands on a ``FantasySquare``.

    Each ``FantasyEvent`` encodes a specific effect type and an optional numeric
    value that parameterises the effect (e.g. the amount of money won or lost).

    Attributes:
        fantasy_type (CharField): The category of effect to apply. One of the
            ``FantasyType`` choices:

            - ``winPlainMoney`` / ``losePlainMoney``: Add or subtract a fixed ``value`` from the player's balance.
            - ``winRatioMoney`` / ``loseRatioMoney``: Add or subtract a ratio of the player's current balance.
            - ``breakOpponentHouse``: Destroy one house on a randomly chosen opponent's property.
            - ``breakOwnHouse``: Destroy one house on the drawing player's own property.
            - ``shufflePositions``: Randomly redistribute all players' board positions.
            - ``moveAnywhereRandom``: Teleport the drawing player to a random square.
            - ``moveOpponentAnywhereRandom``: Teleport a random opponent to a random square.
            - ``shareMoneyAll``: Divide the drawing player's money equally among all players.
            - ``freeHouse``: Grant the drawing player a free house on one of their properties.
            - ``goToJail``: Send the drawing player directly to jail.
            - ``sendToJail``: Send a randomly chosen opponent to jail.
            - ``everybodyToJail``: Send all players to jail simultaneously.
            - ``doubleOrNothing``: Double the player's money or reduce it to zero (50/50 chance).
            - ``getParkingMoney``: Award the player the current ``ParkingSquare`` jackpot.
            - ``reviveProperty``: Lift the mortgage on one of the player's mortgaged properties.
            - ``earthquake``: Destroy all houses on a randomly selected colour group.
            - ``everybodySendsYouMoney``: Every other player pays the drawing player ``value``.
            - ``magnetism``: Move the drawing player to the nearest purchasable property.
            - ``goToStart``: Move the drawing player back to the ``ExitSquare`` (GO).

        value (IntegerField | None): Numeric parameter for the event, e.g. a fixed
            money amount. May be null for events that do not require a value.
        card_cost (IntegerField): The points cost to purchase this card in advance
            (for pre-bought fantasy card mechanics).
    """
    class FantasyType(models.TextChoices):
        winPlainMoney = 'winPlainMoney',
        winRatioMoney = 'winRatioMoney',
        losePlainMoney = 'losePlainMoney',
        loseRatioMoney = 'loseRatioMoney',
        breakOpponentHouse = 'breakOpponentHouse',
        breakOwnHouse = 'breakOwnHouse',
        shufflePositions = 'shufflePositions',
        moveAnywhereRandom = 'moveAnywhereRandom',
        moveOpponentAnywhereRandom = 'moveOpponentAnywhereRandom',
        shareMoneyAll = 'shareMoneyAll',
        freeHouse = 'freeHouse',
        goToJail = 'goToJail',
        sendToJail = 'sendToJail',
        everybodyToJail = 'everybodyToJail',
        doubleOrNothing = 'doubleOrNothing',
        getParkingMoney = 'getParkingMoney',
        reviveProperty = 'reviveProperty',
        earthquake = 'earthquake',
        everybodySendsYouMoney = 'everybodySendsYouMoney',
        magnetism = 'magnetism',
        goToStart = 'goToStart'
    

    fantasy_type = models.CharField(choices=FantasyType, max_length=40)
    value = models.IntegerField(default=0, null=True)
    card_cost = models.IntegerField(default=0)

class FantasyResult(models.Model):
    """
    Records the concrete outcome after a ``FantasyEvent`` has been resolved.

    Stores the event reference alongside a flexible JSON payload describing exactly
    what happened (e.g. which player was affected, how much money changed hands).

    Attributes:
        fantasy_event (ForeignKey -> FantasyEvent | None): The event that was triggered.
        result (JSONField | None): Arbitrary JSON describing the resolved effect,
            e.g. ``{"player_id": 5, "amount": 200}``.
    """
    fantasy_event = models.ForeignKey(FantasyEvent, on_delete=models.SET_NULL, related_name='fantasy_event_resulted', null=True)
    result = models.JSONField(null=True)

###############################################################################

class Game(models.Model):
    """
    Represents the core state and data of a single "Magnate" game session.

    Attributes:
        datetime (DateTimeField): The timestamp of when the game was created or started.
        positions (JSONField): Maps a player's user ID (str/int) to their current square's custom ID (int).
        money (JSONField): Maps a player's user ID (str/int) to their current money balance (int).
        active_phase_player (ForeignKey): The user who must take action in the current micro-phase 
            (e.g., the user who needs to respond to a trade, which might differ from the active_turn_player).
        active_turn_player (ForeignKey): The user whose actual turn it is on the board.
        phase (CharField): The current ``GamePhase`` of the game state machine.
        players (ManyToManyField): The pool of users actively participating in this game.
        ordered_players (JSONField): A list of player primary keys ``[pk1, pk2, pk3, ...]`` 
            representing the strict turn order of the game.
        streak (IntegerField): Tracks consecutive identical dice rolls (e.g., rolling doubles). 
            Usually triggers jail time if it hits 3.
        possible_destinations (JSONField list): Maps a target ``square_id`` (str) to the ``dice_combination`` (int) 
            required to get there. Used when a player has multiple routing options (e.g., taking a tram).
        parking_money (PositiveIntegerField): The accumulated jackpot for landing on the "Free Parking" equivalent.
        jail_remaining_turns (JSONField): Maps a player's user ID (str/int) to the number of turns (int) 
            they have left to serve in jail.
        proposal (ForeignKey): A reference to an active trade proposal (``ActionTradeProposal``) currently 
            blocking the game state awaiting a response.
        fantasy_event (ForeignKey): A reference to an active chance/community chest style event 
            (``FantasyEvent``) currently being resolved.
        current_auction (ForeignKey): A reference to an active property auction (``Auction``) taking place.
        finished (BooleanField): Flag indicating if the game has concluded.
        bonus_response (ForeignKey): Reference to a specific bonus or penalty modifier (``ResponseBonus``)
            applied to the current state.
        kick_out_task_id (CharField): The ID of the scheduled Celery task responsible for kicking 
            a player if they fail to act within the time limit.
        next_phase_task_id (CharField): The ID of the scheduled Celery task responsible for auto-advancing 
            the game to the next phase if a timeout occurs.
        auction_task_id (CharField): The ID of the scheduled Celery task managing auction timing and
            auto-advancing the auction if no bids are placed within the time limit.
        current_turn (PositiveIntegerField): The global counter for the number of turns that have elapsed.
    """
    datetime = models.DateTimeField()
    # Maps user_id -> square_custom_id
    positions = models.JSONField(default=dict, blank=True)
    # Maps user_id -> amount
    money = models.JSONField(default=dict, blank=True)
    active_phase_player = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='phase_to_play')
    active_turn_player = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='turns_to_play')

    class GamePhase(models.TextChoices):
        """
        Enumeration of the possible states (phases) within a game's turn cycle.
        
        Attributes:
            roll_the_dices: The initial phase of a turn. The ``active_turn_player`` 
                must throw the dice to determine movement.
            choose_square: Triggered when a player's movement path presents a fork 
                or routing option (e.g., deciding whether to take a tram/subway line). 
                The player must select their specific destination square.
            choose_fantasy: Triggered when a player lands on a dynamic event square 
                The player must acknowledge and resolve the active ``fantasy_event``.
            management: Triggered when a player lands on an unowned property. The 
                player must choose to either purchase the property at its list price 
                or decline the purchase (which typically immediately triggers an ``auction``).
            business: A versatile phase usually occurring at the end of a turn 
                or before a roll. The player can build/demolish houses, mortgage/unmortgage 
                properties, or finalize their board state before passing the turn.
            liquidation: An emergency phase triggered when a player owes a debt 
                (to the bank or another player) that exceeds their current liquid cash. 
                They are forced to sell assets or mortgage properties to cover the debt, 
                or face bankruptcy.
            auction: A competitive, multi-player phase triggered when a property 
                is declined in the ``management`` phase. The standard turn loop pauses, and 
                players take turns placing bids until a winner is determined.
            proposal_acceptance: An interruptive phase triggered when one player 
                sends a trade request to another. The game loop pauses, the 
                ``active_phase_player`` switches to the recipient, and they must either 
                accept or decline the pending ``proposal``.
            end_game: A terminal state indicating the match has concluded, usually 
                because all other players have gone bankrupt. No further actions can 
                be taken.
        """
        roll_the_dices = 'roll_the_dices'
        choose_square = 'choose_square'
        choose_fantasy = 'choose_fantasy'
        management = 'management'
        liquidation = 'liquidation'
        business = 'business'
        auction = 'auction'
        proposal_acceptance = 'proposal_acceptance'
        end_game = 'end_game'


    phase = models.CharField(choices=GamePhase, max_length=20, default='roll_the_dices')
    players = models.ManyToManyField('CustomUser', related_name='active_playing')
    # ordered_player = [pk1, pk2, pk3, ...]
    ordered_players = models.JSONField(default=list)
    streak = models.IntegerField(default=0)
    #dict[string,int], key=square_id, value=dice_combination to get there
    possible_destinations = models.JSONField(default=list, blank=True)
    parking_money = models.PositiveIntegerField(default=0)
    # Maps user_id -> uint
    jail_remaining_turns = models.JSONField(default=dict, blank=True)
    proposal = models.ForeignKey('ActionTradeProposal', on_delete=models.SET_NULL, null=True, blank=True, related_name='trade_proposal')

    fantasy_event = models.ForeignKey('FantasyEvent', on_delete=models.SET_NULL, null=True, blank=True, related_name='fantasy_event')

    current_auction = models.ForeignKey('Auction', on_delete=models.SET_NULL, null=True, blank=True, related_name='active_game')
    
    finished = models.BooleanField(default=False)
    bonus_response = models.ForeignKey('ResponseBonus', on_delete=models.SET_NULL, null=True, blank=True, related_name='bonus_response')

    kick_out_task_id = models.CharField(max_length=255, null=True, blank=True)
    next_phase_task_id = models.CharField(max_length=255, null=True, blank=True)
    auction_task_id = models.CharField(max_length=255, null=True, blank=True)
    
    current_turn = models.PositiveIntegerField(default=1)

class Auction(models.Model):
    """
    Represents a property auction triggered when a player declines to buy a square.

    During the ``GamePhase.auction`` phase, all players submit bids via ``ActionBid``.
    The highest unique bid wins; ties are recorded separately for resolution.

    Attributes:
        game (ForeignKey -> Game): The game session this auction belongs to.
        square (ForeignKey -> BaseSquare): The property being auctioned.
        bids (JSONField): Dict mapping user ID (str) to their bid amount (int),
            e.g. ``{"12": 150, "7": 200}``.
        final_amount (PositiveIntegerField | None): The winning bid amount, set once
            the auction concludes. Null while the auction is still in progress.
        winner (ForeignKey -> CustomUser | None): The player who won the auction.
            Null while the auction is still active or in the event of a tie.
        is_active (BooleanField): Whether the auction is currently ongoing.
        is_tie (BooleanField): Whether the auction ended without a clear winner due
            to tied top bids, requiring a tie-breaking round.
    """
    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name='auctions')
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='auctioned_in')
    bids = models.JSONField(default=dict, blank=True) #  user_id -> amount
    final_amount = models.PositiveIntegerField(null=True, blank=True)
    winner = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='won_auctions') # type: ignore
    is_active = models.BooleanField(default=True)
    is_tie = models.BooleanField(default=False)

class PropertyRelationship(models.Model):
    """
    Join model that tracks ownership and development state of a square in a specific game.

    One ``PropertyRelationship`` record exists per owned property per game, and is
    updated as houses are built/demolished or mortgages are applied.

    Attributes:
        game (ForeignKey -> Game): The game session this ownership record belongs to.
        owner (ForeignKey -> CustomUser): The player who currently owns this property.
        square (ForeignKey -> BaseSquare): The board square being owned.
        houses (IntegerField): Development level of the property:

            - ``-1``: Player owns the square but not the full colour group (incomplete set).
            - ``0``: Full colour group is owned; rent multiplier applies but no houses built yet.
            - ``1``–``4``: Number of houses built on the property.
            - ``5``: A hotel has been built (replaces 4 houses).

        mortgage (BooleanField): Whether the property is currently mortgaged. While
            mortgaged, the owner collects no rent and cannot build houses.
    """
    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name='property_relationships')
    owner = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='owned_by') # type: ignore
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='owned_square')

    houses = models.IntegerField(default=-1)
    mortgage = models.BooleanField(default=False)

###############################################################################

class Action(models.Model):
    """
    Base model representing a player action within a game.

    All concrete action types inherit from this model, sharing the game context
    and the player who performed the action. The action log is queryable for
    replays, auditing, and bot decision-making.

    Attributes:
        game (ForeignKey -> Game): The game session in which the action was performed.
        player (ForeignKey -> CustomUser): The player who performed the action.
    """
    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name='in_game')
    player = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='made_by')

class ActionThrowDices(Action):
    """
    Action representing a player throwing the dice to begin their turn.

    No additional data is stored beyond the inherited ``Action`` fields; the
    actual dice values are computed server-side and returned in a ``ResponseThrowDices``.
    """
    pass

class ActionMoveTo(Action):
    """
    Action representing a player moving to a specific square after a dice roll.

    Attributes:
        square (ForeignKey -> BaseSquare): The destination square the player
            moves to following normal dice movement.
    """
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='move_to')

class ActionTakeTram(Action):
    """
    Action representing a player choosing to board the tram network.

    Triggered during the ``GamePhase.choose_square`` phase when a player's dice
    roll lands them on or near a ``TramSquare`` with an available shortcut route.

    Attributes:
        square (ForeignKey -> BaseSquare): The tram destination square the player
            has chosen to travel to.
    """
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='tram_move_to')

class ActionDropPurchase(Action):
    """
    Action representing a player declining to buy an unowned property.

    Declining immediately triggers an ``Auction`` for the property, entering the
    ``GamePhase.auction`` phase.

    Attributes:
        square (ForeignKey -> BaseSquare): The property that was declined.
    """
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='dropped')

class ActionBuySquare(Action):
    """
    Action representing a player purchasing an unowned property from the bank.

    The property's ``buy_price`` is deducted from the player's balance and a
    ``PropertyRelationship`` record is created.

    Attributes:
        square (ForeignKey -> BaseSquare): The property being purchased.
    """
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='bought')

class ActionBuild(Action):
    """
    Action representing a player building houses or a hotel on an owned property.

    Only valid during ``GamePhase.business`` when the player owns the full colour
    group. Building is limited by the even-build rule (houses must be distributed
    evenly across the group).

    Attributes:
        houses (IntegerField): The number of houses being added in this action.
            A value of ``5`` indicates a hotel is being placed.
        square (ForeignKey -> BaseSquare): The property on which construction takes place.
    """
    houses = models.IntegerField(default=1)
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='build_square')

class ActionDemolish(Action):
    """
    Action representing a player demolishing houses or a hotel on an owned property.

    Demolishing returns a portion of the build cost. The even-build rule also
    applies to demolition (houses must be removed evenly across the group).

    Attributes:
        houses (IntegerField): The number of houses being removed in this action.
        square (ForeignKey -> BaseSquare): The property from which construction is removed.
    """
    houses = models.IntegerField(default=0)
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='demolish_square')

class ActionChooseCard(Action):
    """
    Action representing a player interacting with a fantasy card draw.

    Players may have the option to reveal a card they purchased in advance
    (``chosen_revealed_card = True``) or draw a random card from the deck.

    Attributes:
        chosen_revealed_card (BooleanField): ``True`` if the player chose to play
            a pre-purchased revealed card; ``False`` if drawing randomly from the deck.
    """
    chosen_revealed_card = models.BooleanField(default=False)

class ActionSurrender(Action):
    """
    Action representing a player voluntarily quitting the game.

    The player's assets are returned to the bank and they are removed from
    ``Game.players``. No additional data beyond the inherited ``Action`` fields
    is required.
    """
    pass

class ActionTradeProposal(Action):
    """
    Action representing a trade offer sent from one player to another.

    Creates a pending ``proposal`` on the ``Game``, pausing the game in
    ``GamePhase.proposal_acceptance`` until the recipient responds.

    Attributes:
        destination_user (ForeignKey -> CustomUser): The player receiving the trade offer.
        offered_money (PositiveIntegerField): Amount of money the proposing player
            is offering to give to the destination player.
        asked_money (PositiveIntegerField): Amount of money the proposing player
            is requesting from the destination player.
        offered_properties (ManyToManyField -> PropertyRelationship): Properties the
            proposing player is offering to transfer to the destination player.
        asked_properties (ManyToManyField -> PropertyRelationship): Properties the
            proposing player is requesting from the destination player in return.
    """
    destination_user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='destination_user')
    offered_money = models.PositiveIntegerField(default=0)
    asked_money = models.PositiveIntegerField(default=0)
    offered_properties = models.ManyToManyField('PropertyRelationship', related_name='offered_properties')
    asked_properties = models.ManyToManyField('PropertyRelationship', related_name='asked_properties')

class ActionTradeAnswer(Action):
    """
    Action representing a player's response to a pending trade proposal.

    Resolves the ``GamePhase.proposal_acceptance`` phase. If accepted, properties
    and money are transferred between the two parties.

    Attributes:
        choose (BooleanField): ``True`` if the trade was accepted; ``False`` if declined.
    """
    choose = models.BooleanField(default=False)

class ActionMortgageSet(Action):
    """
    Action representing a player mortgaging one of their properties.

    The player receives half the property's ``buy_price`` from the bank. While
    mortgaged, no rent is collected and no houses can be built on the property.

    Attributes:
        square (ForeignKey -> BaseSquare): The property being mortgaged.
    """
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='mortgage_set_square')

class ActionMortgageUnset(Action):
    """
    Action representing a player lifting the mortgage on one of their properties.

    The player pays the bank to reinstate the property (typically the mortgage
    value plus an interest surcharge). The property can then collect rent again.

    Attributes:
        square (ForeignKey -> BaseSquare): The property being unmortgaged.
    """
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='mortgage_unset_square')

class ActionPayBail(Action):
    """
    Action representing a player paying the bail fee to leave jail immediately.

    The player's balance is reduced by ``JailSquare.bail_price`` and they are
    released to resume normal turns. No additional data is needed beyond the
    inherited ``Action`` fields.
    """
    pass

class ActionNextPhase(Action):
    """
    Action representing a player explicitly advancing to the next game phase or ending their turn.

    Used as a confirmation signal (e.g. ending the ``business`` phase) when the player has
    no further actions to perform. No additional data is needed beyond the inherited
    ``Action`` fields.
    """
    pass

class ActionBid(Action):
    """
    Action representing a player placing a bid during an active auction.

    Submitted bids are recorded in ``Auction.bids``. The auction ends once all
    players have bid or the auction timer expires.

    Attributes:
        amount (PositiveIntegerField): The bid amount in in-game currency.
    """
    amount = models.PositiveIntegerField(default=0)

###############################################################################

class Response(models.Model):
    """
    Base model for game state snapshots broadcasted to all connected clients.

    Each concrete ``Response`` subclass corresponds to a specific game event and
    carries enough state for the frontend to render the updated board without
    needing to re-fetch the full ``Game`` object.

    Attributes:
        money (JSONField): Current balances for all players, mapping user ID (str)
            to amount (int).
        active_phase_player (ForeignKey -> CustomUser | None): The user expected to
            act next in the current micro-phase.
        active_turn_player (ForeignKey -> CustomUser | None): The user whose overall
            board turn it is.
        phase (CharField): The ``GamePhase`` the game has transitioned to after this event.
        positions (JSONField): Current board positions for all players, mapping user ID
            (str) to square ``custom_id`` (int).
    """
    money = models.JSONField(default=dict, blank=True)
    active_phase_player = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='response_phase_to_play')
    active_turn_player = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='response_turns_to_play')
    phase = models.CharField(choices=Game.GamePhase, max_length=20)
    positions = models.JSONField(default=dict, blank=True) # user -> cumtom_id (int)

class ResponseSkipPhase(Response):
    """
    Response broadcast when a game phase is skipped without any board movement.

    Inherits all fields from ``Response``. Used for phase transitions where no
    positional or balance changes occur (e.g. skipping straight from one phase
    to another due to game logic).
    """
    pass

class ResponseMovement(Response):
    """
    Base response for any event that involves a player moving across the board.

    Provides the ordered path of squares the player traversed so the frontend
    can animate the token movement step by step.

    Attributes:
        path (JSONField): Ordered list of square ``custom_id`` values the player
            passed through, from their starting position to their final destination.
        fantasy_event (ForeignKey -> FantasyEvent | None): Set if the player's
            movement ended on a ``FantasySquare``, indicating which event was drawn.
    """
    path = models.JSONField(default=list, blank=True)
    fantasy_event = models.ForeignKey('FantasyEvent', on_delete=models.CASCADE, null=True, blank=True)

class ResponseThrowDices(ResponseMovement):
    """
    Response delivering the result of a dice roll and valid movement destinations.

    Extends ``ResponseMovement`` with dice values and routing information so the
    frontend can display the roll result and highlight reachable squares.

    Attributes:
        dice1 (PositiveIntegerField): Value of the first standard die (1–6).
        dice2 (PositiveIntegerField): Value of the second standard die (1–6).
        dice_bus (PositiveIntegerField): Value of the special bus/wildcard die, used
            for tram or alternative routing mechanics.
        destinations (JSONField): List of possible destination squares the player can
            move to given the dice result. Each entry maps a square ``custom_id`` to
            the dice combination needed to reach it.
        triple (BooleanField): ``True`` if all three dice showed the same value,
            triggering a special triple-dice effect.
        streak (IntegerField): Updated consecutive-doubles count after this roll.
            Reaching 3 sends the player to jail.
    """
    dice1 = models.PositiveIntegerField(default=0)
    dice2 = models.PositiveIntegerField(default=0)
    dice_bus = models.PositiveIntegerField(default=0)
    destinations = models.JSONField(default=list, blank=True)
    triple = models.BooleanField(default=False)
    streak = models.IntegerField(default=0)

class ResponseChooseSquare(ResponseMovement):
    """
    Response confirming a player's movement to a specifically chosen square.

    Used after the player selects their destination during the ``GamePhase.choose_square``
    phase (e.g. after deciding to take the tram). Inherits path animation data from
    ``ResponseMovement``.
    """
    pass

class ResponseChooseFantasy(Response):
    """
    Response delivering the resolved outcome of a drawn fantasy card.

    Sent after the server resolves the ``FantasyEvent`` the player triggered by
    landing on a ``FantasySquare``.

    Attributes:
        fantasy_result (ForeignKey -> FantasyResult): The concrete result of the
            fantasy event, including the effect type and any numeric outcomes.
    """
    fantasy_result = models.ForeignKey('FantasyResult', on_delete=models.CASCADE)

class ResponseAuction(Response):
    """
    Response updating all clients with the current or final state of an auction.

    Sent after every bid and upon auction conclusion. Exposes auction data as
    properties delegated to the linked ``Auction`` record.

    Attributes:
        auction (OneToOneField -> Auction): The auction whose state is being broadcast.

    Properties:
        winner: Delegates to ``Auction.winner``.
        final_amount: Delegates to ``Auction.final_amount``.
        is_tie: Delegates to ``Auction.is_tie``.
        bids: Delegates to ``Auction.bids``.
    """
    auction = models.OneToOneField('Auction', on_delete=models.CASCADE, related_name='response')

    @property
    def winner(self):
        """
        Retrieves the winner of the auction.

        Returns:
            CustomUser | None: The winning user.
        """
        return self.auction.winner
    
    @property
    def final_amount(self):
        """
        Retrieves the final bid amount of the auction.

        Returns:
            int: The winning bid amount.
        """
        return self.auction.final_amount
    
    @property
    def is_tie(self):
        """
        Indicates if the auction ended in a tie.

        Returns:
            bool: True if tied, False otherwise.
        """
        return self.auction.is_tie

    @property
    def bids(self):
        """
        Retrieves all bids placed during the auction.

        Returns:
            dict: Mapping of user IDs to bid amounts.
        """
        return self.auction.bids
    
class ResponseBonus(Response):
    """
    Response delivering bonus or penalty modifiers applied to a player at a specific game moment.

    Used to broadcast end-of-game or milestone achievement bonuses (see ``BonusCategory``)
    that affect player balances or scores.

    Attributes:
        bonuses (JSONField): Dict mapping user ID (str) to a bonus amount (int) or a
            nested structure describing multiple bonus categories awarded.
    """
    bonuses = models.JSONField(default=dict, blank=True)

###############################################################################

class PlayerGameStatistic(models.Model):
    """
    Per-player, per-game statistics accumulated throughout a single game session.

    Linked to ``CustomUser.played_games`` via the ``through`` parameter, providing
    rich stat tracking for post-game summaries, leaderboards, and bonus calculations.

    Attributes:
        user (ForeignKey -> CustomUser): The player these stats belong to.
        game (ForeignKey -> Game): The game session these stats belong to.
        walked_squares (PositiveIntegerField): Total number of squares the player has
            moved across during the game.
        won_money (PositiveIntegerField): Cumulative money received (rents collected,
            fantasy winnings, passing GO, etc.).
        lost_money (PositiveIntegerField): Cumulative money spent or paid out (rent
            paid, purchase costs, bail fees, etc.).
        num_fantasy_events (PositiveIntegerField): Number of fantasy cards drawn.
        built_houses (PositiveIntegerField): Total houses (including hotels) built.
        demolished_houses (PositiveIntegerField): Total houses (including hotels) demolished.
        times_in_jail (PositiveIntegerField): Number of times the player was sent to jail.
        turns_in_jail (PositiveIntegerField): Total turns spent serving a jail sentence.
        num_paid_rents (PositiveIntegerField): Number of times the player paid rent to
            another player.
        num_trades (PositiveIntegerField): Number of completed trade transactions.
        num_mortgages (PositiveIntegerField): Number of times the player mortgaged a property.

    Meta:
        unique_together: Enforces one stats record per (user, game) pair.
    """
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE)
    game = models.ForeignKey('Game', on_delete=models.CASCADE)
    
    walked_squares = models.PositiveIntegerField(default=0)
    won_money = models.PositiveIntegerField(default=0)
    lost_money = models.PositiveIntegerField(default=0)
    num_fantasy_events = models.PositiveIntegerField(default=0)
    built_houses = models.PositiveIntegerField(default=0)
    demolished_houses = models.PositiveIntegerField(default=0)
    times_in_jail = models.PositiveIntegerField(default=0)
    turns_in_jail = models.PositiveIntegerField(default=0)
    num_paid_rents = models.PositiveIntegerField(default=0)
    num_trades = models.PositiveIntegerField(default=0)
    num_mortgages = models.PositiveIntegerField(default=0)
    
    class Meta:
        # 1 player and game for each stats
        unique_together = ('user', 'game')

class GameSummary(models.Model):
    """
    High-level summary record created when a game concludes.

    Captures the time span of the game and each player's final cash balance,
    suitable for displaying a post-game results screen.

    Attributes:
        game (ForeignKey -> Game): The completed game session this summary belongs to.
        start_date (DateTimeField): Timestamp of when the game started.
        end_date (DateTimeField): Timestamp of when the game ended.
        final_money (JSONField): Dict mapping user ID (str) to their ending cash
            balance (int) at the time the game concluded.
    """
    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name='summary')
    
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()

    final_money = models.JSONField(default=dict, blank=True)
    

class BonusCategory(models.Model):
    """
    Defines a bonus awarded to a player for achieving a milestone in a specific stat field.

    Each ``BonusCategory`` maps one ``PlayerGameStatistic`` field (or the ``end_game``
    event) to a fixed ``bonus_amount`` in platform points. At the end of a game, the
    server checks each category and awards the bonus to qualifying players.

    Attributes:
        stat_field (CharField): The ``PlayerGameStatistic`` field this bonus applies to,
            or ``end_game`` to award a bonus simply for finishing a game. One of:
            ``walked_squares``, ``won_money``, ``lost_money``, ``num_fantasy_events``,
            ``built_houses``, ``demolished_houses``, ``times_in_jail``, ``turns_in_jail``,
            ``num_paid_rents``, ``num_trades``, ``num_mortgages``, ``end_game``.
            Must be unique — only one bonus rule per stat field.
        bonus_amount (PositiveIntegerField): The number of platform points awarded when
            the qualifying condition for this category is met.
    """
    class StatField(models.TextChoices):
        walked_squares    = 'walked_squares'
        won_money         = 'won_money'
        lost_money        = 'lost_money'
        num_fantasy_events = 'num_fantasy_events'
        built_houses      = 'built_houses'
        demolished_houses = 'demolished_houses'
        times_in_jail     = 'times_in_jail'
        turns_in_jail     = 'turns_in_jail'
        num_paid_rents    = 'num_paid_rents'
        num_trades        = 'num_trades'
        num_mortgages     = 'num_mortgages'
        end_game = 'end_game'

    stat_field = models.CharField(choices=StatField, max_length=30, unique=True)
    bonus_amount = models.PositiveIntegerField(default=200)
