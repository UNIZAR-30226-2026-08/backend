from rest_framework import serializers
from .models import *

# handling baseSquare by custom_id
class SquareCustomIdField(serializers.SlugRelatedField):
    def __init__(self, **kwargs):
        super().__init__(slug_field='custom_id', queryset=BaseSquare.objects.all(), **kwargs)

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

class ActionSellSquareSerializer(ActionSerializer):
    square = SquareCustomIdField()
    class Meta(ActionSerializer.Meta):
        model = ActionSellSquare
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
        fields = ActionSerializer.Meta.fields + ['chosen_card']

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
        fields = ActionSerializer.Meta.fields + ['choose','proposal']

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
        fields = ActionSerializer.Meta.fields + ['amount', 'auction']

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
        return {str(bid.player.pk): bid.amount for bid in obj.bids.all()}

class GeneralActionSerializer(serializers.ModelSerializer):
    serializer_mapping = {
        'ActionThrowDices': ActionThrowDicesSerializer,
        'ActionMoveTo': ActionMoveToSerializer,
        'ActionTakeTram': ActionTakeTramSerializer,
        'ActionBuySquare': ActionBuySquareSerializer,
        'ActionSellSquare': ActionSellSquareSerializer,
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
        fields = ['fantasy_type','values','card_cost']

class FantasyResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = FantasyResult
        fields = ['fantasy_type','values']

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

class ResponseMovementSerializer(serializers.ModelSerializer):
    class Meta(ResponseSerializer.Meta):
        model = ResponseMovement

class ResponseThrowDicesSerializer(serializers.ModelSerializer):
    class Meta(ResponseSerializer.Meta):
        model = ResponseThrowDices

class ResponseChooseSquareSerializer(serializers.ModelSerializer):
    class Meta(ResponseSerializer.Meta):
        model = ResponseChooseSquare

class ResponseChooseFantasySerializer(serializers.ModelSerializer):
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
