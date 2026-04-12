from rest_framework import serializers
from .models import *
from django.contrib.auth.password_validation import validate_password
from .models import CustomUser

# handling baseSquare by custom_id
class SquareCustomIdField(serializers.SlugRelatedField):
    def __init__(self, **kwargs):
        super().__init__(slug_field='custom_id', queryset=BaseSquare.objects.all(), **kwargs)

###############################################################################
#############      Property relationship serializers     ######################
###############################################################################
class PropertyRelationshipSerializer(serializers.ModelSerializer):
    """
    Example:
        ```json
        {
            "owner": 1, 
            "square": 3, 
            "houses": 2, 
            "mortgage": False
        }
        ```
    """
    class Meta:
        model = PropertyRelationship
        # Does not serialize game
        fields = ['owner', 'square', 'houses', 'mortgage']


###############################################################################
#############      Game serializers     #######################################
###############################################################################

class GameStatusSerializer(serializers.ModelSerializer):
    """
    Serializes the game status allowing reconnection. It excludes certain
    fields from Game model and also includes active `property_relationships`.
    Example:
        A standard serialized response during the 'roll_the_dices' phase:
        ```json
        {
            "id": 1,
            "datetime": "2026-04-06T18:30:00Z",
            "positions": {"42": 0, "85": 12},
            "money": {"42": 1500, "85": 1350},
            "active_phase_player": 42,
            "active_turn_player": 42,
            "phase": "roll_the_dices",
            "players": [42, 85],
            "ordered_players": [42, 85],
            "streak": 0,
            "possible_destinations": [],
            "parking_money": 200,
            "jail_remaining_turns": {'2': 3},
            "finished": false,
            "bonus_response": null,
            "current_turn": 5,
            "property_relationships": [
                {"owner": 1, "square": 3, "houses": 2, "mortgage": False},
                {"owner": 2, "square": 4, "houses": 3, "mortgage": False}
                ],
        }
        ```
    """
    property_relationships = PropertyRelationshipSerializer(many=True, read_only=True)
    class Meta:
        model = Game
        exclude = ['proposal', 'fantasy_event', 'current_auction',
                   'bonus_response',
                   'kick_out_task_id', 'next_phase_task_id']

###############################################################################
#############      Square serializers     #####################################
###############################################################################
class BaseSquareSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    class Meta:
        model = BaseSquare
        fields = ['type','custom_id', 'board']
    def get_type(self, obj):
        return obj.__class__.__name__

class PropertySquareSerializer(BaseSquareSerializer):
    class Meta(BaseSquareSerializer.Meta):
        model = PropertySquare
        fields = BaseSquareSerializer.Meta.fields + ['group', 'buy_price', 'build_price', 'rent_prices']

class FantasySquareSerializer(BaseSquareSerializer):
    class Meta(BaseSquareSerializer.Meta):
        model = FantasySquare
        fields = BaseSquareSerializer.Meta.fields

class BridgeSquareSerializer(BaseSquareSerializer):
    class Meta(BaseSquareSerializer.Meta):
        model = BridgeSquare
        fields = BaseSquareSerializer.Meta.fields + ['buy_price','rent_prices']

class TramSquareSerializer(BaseSquareSerializer):
    class Meta(BaseSquareSerializer.Meta):
        model = TramSquare
        fields = BaseSquareSerializer.Meta.fields + ['buy_price']

class ParkingSquareSerializer(BaseSquareSerializer):
    class Meta(BaseSquareSerializer.Meta):
        model = ParkingSquare
        fields = BaseSquareSerializer.Meta.fields + ['money']

class ServerSquareSerializer(BaseSquareSerializer):
    class Meta(BaseSquareSerializer.Meta):
        model = ServerSquare
        fields = BaseSquareSerializer.Meta.fields + ['buy_price','rent_prices']

class ExitSquareSerializer(BaseSquareSerializer):
    class Meta(BaseSquareSerializer.Meta):
        model = ExitSquare
        fields = BaseSquareSerializer.Meta.fields + ['init_money']

class GoToJailSquareSerializer(BaseSquareSerializer):
    class Meta(BaseSquareSerializer.Meta):
        model = GoToJailSquare
        fields = BaseSquareSerializer.Meta.fields

class JailSquareSerializer(BaseSquareSerializer):
    class Meta(BaseSquareSerializer.Meta):
        model = JailSquare
        fields = BaseSquareSerializer.Meta.fields + ['bail_price']

class GeneralSquareSerializer(serializers.ModelSerializer):
    mapping = {
        'PropertySquare': PropertySquareSerializer,
        'FantasySquare': FantasySquareSerializer,
        'BridgeSquare': BridgeSquareSerializer,
        'TramSquare': TramSquareSerializer,
        'ParkingSquare': ParkingSquareSerializer,
        'ServerSquare': ServerSquareSerializer,
        'ExitSquare': ExitSquareSerializer,
        'GoToJailSquare': GoToJailSquareSerializer,
        'JailSquare': JailSquareSerializer,
        'BaseSquare': BaseSquareSerializer, # Fallback
    }
    
    type = serializers.SerializerMethodField()

    def to_representation(self, instance):
        square_type = instance.__class__.__name__
        serializer_class = self.mapping.get(square_type, BaseSquareSerializer)
        data = serializer_class(instance, context=self.context).data
        return {"type": square_type, **dict(data)}

    class Meta:
        model = BaseSquare
        fields = '__all__'

###############################################################################
#############      Action serializers     #####################################
###############################################################################
class ActionSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    class Meta:
        model = Action
        fields = ['type', 'game', 'player']
    def get_type(self, obj):
        return obj.__class__.__name__

class ActionThrowDicesSerializer(ActionSerializer):
    class Meta(ActionSerializer.Meta):
        model = ActionThrowDices
        fields = ActionSerializer.Meta.fields

class ActionMoveToSerializer(ActionSerializer):
    square = SquareCustomIdField()
    class Meta(ActionSerializer.Meta):
        model = ActionMoveTo
        fields = ActionSerializer.Meta.fields + ['square']

class ActionTakeTramSerializer(ActionSerializer):
    square = SquareCustomIdField()
    class Meta(ActionSerializer.Meta):
        model = ActionTakeTram
        fields = ActionSerializer.Meta.fields + ['square']

class ActionBuySquareSerializer(ActionSerializer):
    square = SquareCustomIdField()
    class Meta(ActionSerializer.Meta):
        model = ActionBuySquare
        fields = ActionSerializer.Meta.fields + ['square']

class ActionBuildSerializer(ActionSerializer):
    square = SquareCustomIdField()
    class Meta(ActionSerializer.Meta):
        model = ActionBuild
        fields = ActionSerializer.Meta.fields + ['houses','square']

class ActionDemolishSerializer(ActionSerializer):
    square = SquareCustomIdField()
    class Meta(ActionSerializer.Meta):
        model = ActionDemolish
        fields = ActionSerializer.Meta.fields + ['houses','square']

class ActionChooseCardSerializer(ActionSerializer):
    class Meta(ActionSerializer.Meta):
        model = ActionChooseCard
        fields = ActionSerializer.Meta.fields + ['chosen_revealed_card']

class ActionSurrenderSerializer(ActionSerializer):
    class Meta(ActionSerializer.Meta):
        model = ActionSurrender
        fields = ActionSerializer.Meta.fields

class ActionTradeProposalSerializer(ActionSerializer):
    offered_properties = serializers.PrimaryKeyRelatedField(
        many=True, 
        queryset=PropertyRelationship.objects.all(),
        required=False
    )
    asked_properties = serializers.PrimaryKeyRelatedField(
        many=True, 
        queryset=PropertyRelationship.objects.all(),
        required=False
    )
    class Meta(ActionSerializer.Meta):
        model = ActionTradeProposal
        fields = ActionSerializer.Meta.fields + ['destination_user','offered_money','asked_money','offered_properties','asked_properties']
    def create(self, validated_data):
        offered_ids = validated_data.pop('offered_properties', [])
        asked_ids = validated_data.pop('asked_properties', [])
        instance = ActionTradeProposal.objects.create(**validated_data)
        if offered_ids:
            instance.offered_properties.set(offered_ids)
        if asked_ids:
            instance.asked_properties.set(asked_ids)
        return instance

class ActionTradeAnswerSerializer(ActionSerializer):
    class Meta(ActionSerializer.Meta):
        model = ActionTradeAnswer
        fields = ActionSerializer.Meta.fields + ['choose']

class ActionMortgageSetSerializer(ActionSerializer):
    square = SquareCustomIdField()
    class Meta(ActionSerializer.Meta):
        model = ActionMortgageSet
        fields = ActionSerializer.Meta.fields + ['square']

class ActionMortgageUnsetSerializer(ActionSerializer):
    square = SquareCustomIdField()
    class Meta(ActionSerializer.Meta):
        model = ActionMortgageUnset
        fields = ActionSerializer.Meta.fields + ['square']

class ActionPayBailSerializer(ActionSerializer):
    class Meta(ActionSerializer.Meta):
        model = ActionPayBail
        fields = ActionSerializer.Meta.fields

class ActionNextPhaseSerializer(ActionSerializer):
    class Meta(ActionSerializer.Meta):
        model = ActionNextPhase
        fields = ActionSerializer.Meta.fields

class ActionBidSerializer(ActionSerializer):
    class Meta(ActionSerializer.Meta):
        model = ActionBid
        fields = ActionSerializer.Meta.fields + ['amount']

class ActionDropPurchaseSerializer(ActionSerializer):
    square = SquareCustomIdField()
    class Meta(ActionSerializer.Meta):
        model = ActionDropPurchase
        fields = ActionSerializer.Meta.fields + ['square']

class AuctionSerializer(serializers.ModelSerializer):
    square = SquareCustomIdField()
    bids = serializers.SerializerMethodField()
    class Meta:
        model = Auction
        fields = ['id', 'square', 'winner', 'final_amount', 'is_active', 'is_tie', 'bids']
    
    def get_bids(self, obj):
        # Return dict of user_id -> amount to maintain frontend compatibility
        return obj.bids

class GeneralActionSerializer(serializers.ModelSerializer):
    serializer_mapping = {
        'ActionThrowDices': ActionThrowDicesSerializer,
        'ActionMoveTo': ActionMoveToSerializer,
        'ActionTakeTram': ActionTakeTramSerializer,
        'ActionBuySquare': ActionBuySquareSerializer,
        'ActionBuild': ActionBuildSerializer,
        'ActionDemolish': ActionDemolishSerializer,
        'ActionChooseCard': ActionChooseCardSerializer,
        'ActionSurrender': ActionSurrenderSerializer,
        'ActionTradeProposal': ActionTradeProposalSerializer,
        'ActionTradeAnswer': ActionTradeAnswerSerializer,
        'ActionMortgageSet': ActionMortgageSetSerializer,
        'ActionMortgageUnset': ActionMortgageUnsetSerializer,
        'ActionPayBail': ActionPayBailSerializer,
        'ActionBid': ActionBidSerializer,
        'ActionDropPurchase': ActionDropPurchaseSerializer, 
        'ActionNextPhase': ActionNextPhaseSerializer,
    }
    def to_representation(self, instance):
        action_type = instance.__class__.__name__
        serializer_class = self.serializer_mapping.get(action_type, ActionSerializer)
        return serializer_class(instance, context=self.context).data

    def to_internal_value(self, data):
        action_type = data.get('type')

        if not action_type:
            raise serializers.ValidationError({
                'type': 'This field is required to identify the action.'
            })

        serializer_class = self.serializer_mapping.get(action_type)

        if not serializer_class:
            raise serializers.ValidationError({
                'type': f"Invalid action type '{action_type}'. Valid options are: {list(self.serializer_mapping.keys())}"
            })

        serializer = serializer_class(context=self.context)
        
        return serializer.to_internal_value(data)

    def create(self, validated_data):
        action_type = self.initial_data.get('type') #type: ignore
        serializer_class = self.serializer_mapping.get(action_type)

        if not serializer_class:
            raise serializers.ValidationError({
                'type': f"Tipo de acción inválido o no proporcionado: {action_type}"
            })
        
        serializer = serializer_class(context=self.context)
        return serializer.create(validated_data)

    class Meta:
        model = Action
        fields = '__all__'

###############################################################################
#############      Fantasy serializers     ####################################
###############################################################################
class FantasyEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = FantasyEvent
        fields = ['fantasy_type', 'value', 'card_cost']

class FantasyResultSerializer(serializers.ModelSerializer):
    fantasy_event = FantasyEventSerializer(read_only=True)
    class Meta:
        model = FantasyResult
        fields = ['fantasy_event', 'result']

###############################################################################
############      Response serializers     ####################################
###############################################################################
class ResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Response
        exclude = ['id']

class ResponseAuctionSerializer(ResponseSerializer):
    auction = AuctionSerializer()
    class Meta(ResponseSerializer.Meta):
        model = ResponseAuction
        exclude = ['auction']

class ResponseMovementSerializer(serializers.ModelSerializer):
    class Meta(ResponseSerializer.Meta):
        model = ResponseMovement

class ResponseThrowDicesSerializer(serializers.ModelSerializer):
    fantasy_event = FantasyEventSerializer(read_only=True)
    class Meta(ResponseSerializer.Meta):
        model = ResponseThrowDices

class ResponseChooseSquareSerializer(serializers.ModelSerializer):
    fantasy_event = FantasyEventSerializer(read_only=True)
    class Meta(ResponseSerializer.Meta):
        model = ResponseChooseSquare

class ResponseChooseFantasySerializer(serializers.ModelSerializer):
    fantasy_result = FantasyResultSerializer(read_only=True)
    class Meta(ResponseSerializer.Meta):
        model = ResponseChooseFantasy

class GeneralResponseSerializer(serializers.ModelSerializer):
    mapping = {
        'ResponseAuction': ResponseAuctionSerializer,
        'ResponseThrowDices': ResponseThrowDicesSerializer,
        'ResponseChooseSquare': ResponseChooseSquareSerializer,
        'ResponseChooseFantasy': ResponseChooseFantasySerializer,
        'Response': ResponseSerializer,
    }
    type = serializers.SerializerMethodField()
    def to_representation(self, instance):
        action_type = instance.__class__.__name__
        serializer_class = self.mapping.get(action_type, ResponseSerializer)
        data = serializer_class(instance, context=self.context).data
        return {"type": action_type, **dict(data)}

    class Meta:
        model = Response


###############################################################################
############      Tokens     ####################################
###############################################################################

class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label='Confirmar contraseña')

    class Meta:
        model  = CustomUser
        fields = ('username', 'email', 'password', 'password2')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password': 'Las contraseñas no coinciden.'})
        if CustomUser.objects.filter(email=attrs['email']).exists():
            raise serializers.ValidationError({'email': 'Este email ya está registrado.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        return CustomUser.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
        )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


################################################################################
########################### general info #######################################
################################################################################

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CustomUser
        fields = (
            'username', 'email',
            'points', 'exp', 'elo',
            'date_joined',
            'num_played_games',
            'num_won_games',
            'user_piece'
        )
        read_only_fields = fields

##############################################################################
################################### items ####################################
##############################################################################
class ItemSerializer(serializers.ModelSerializer):
    owned = serializers.SerializerMethodField()

    class Meta:
        model  = Item
        fields = ('custom_id', 'itemType', 'price', 'owned')

    def get_owned(self, obj) -> bool:
        request: Request = self.context['request']  # type: ignore
        user: CustomUser = request.user  # type: ignore
        return obj.owners.filter(pk=user.pk).exists()


class PurchaseSerializer(serializers.Serializer):
    custom_id = serializers.IntegerField()  # recibe custom_id del frontend

    def validate_custom_id(self, value):
        try:
            item = Item.objects.get(custom_id=value)
        except Item.DoesNotExist:
            raise serializers.ValidationError('Item not found.')

        user: CustomUser = self.context['request'].user  # type: ignore

        if user.owned_items.filter(custom_id=item.custom_id).exists():
            raise serializers.ValidationError('You already own this item.')

        if user.points < item.price:
            raise serializers.ValidationError(
                f'Not enough points. You have {user.points}, item costs {item.price}.'
            )

        return value


class ChangePieceSerializer(serializers.Serializer):
    custom_id = serializers.IntegerField()

    def validate_custom_id(self, value):
        try:
            item = Item.objects.get(custom_id=value)
        except Item.DoesNotExist:
            raise serializers.ValidationError('Item not found.')

        if item.itemType != 'piece':
            raise serializers.ValidationError('Item is not a piece.')

        user: CustomUser = self.context['request'].user  # type: ignore

        if not user.owned_items.filter(custom_id=item.custom_id).exists():
            raise serializers.ValidationError('You do not own this piece.')

        return value
