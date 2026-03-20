from rest_framework import serializers
from .models import *

# handling baseSquare by custom_id
class SquareCustomIdField(serializers.SlugRelatedField):
    def __init__(self, **kwargs):
        super().__init__(slug_field='custom_id', queryset=BaseSquare.objects.all(), **kwargs)

####################### Square serializers
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
    def to_representation(self, instance):
        if isinstance(instance, PropertySquare):
            return PropertySquareSerializer(instance, context=self.context).data
        elif isinstance(instance, FantasySquare):
            return FantasySquareSerializer(instance, context=self.context).data
        elif isinstance(instance, BridgeSquare):
            return BridgeSquareSerializer(instance, context=self.context).data
        elif isinstance(instance, TramSquare):
            return TramSquareSerializer(instance, context=self.context).data
        elif isinstance(instance, ParkingSquare):
            return ParkingSquareSerializer(instance, context=self.context).data
        elif isinstance(instance, ServerSquare):
            return ServerSquareSerializer(instance, context=self.context).data
        elif isinstance(instance, ExitSquare):
            return ExitSquareSerializer(instance, context=self.context).data
        elif isinstance(instance, GoToJailSquare):
            return GoToJailSquareSerializer(instance, context=self.context).data
        elif isinstance(instance, JailSquare):
            return JailSquareSerializer(instance, context=self.context).data
        
        #TODO: excepcion
        return BaseSquareSerializer(instance, context=self.context).data

    class Meta:
        model = BaseSquare
        fields = '__all__'

############################################### Action Serializers
class ActionSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    class Meta:
        model = Action
        fields = ['type','game','player']#game?????? creo que sobra TODO
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

class ActionDoNotTakeTramSerializer(ActionSerializer):
    class Meta(ActionSerializer.Meta):
        model = ActionDoNotTakeTram
        fields = ActionSerializer.Meta.fields

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

class ActionGoToJailSerializer(ActionSerializer):
    class Meta(ActionSerializer.Meta):
        model = ActionGoToJail
        fields = ActionSerializer.Meta.fields

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

class ActionBidSerializer(ActionSerializer):
    class Meta(ActionSerializer.Meta):
        model = ActionBid
        fields = ActionSerializer.Meta.fields + ['amount', 'auction']

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
    def to_representation(self, instance):
        if isinstance(instance, ActionThrowDices):
            return ActionThrowDicesSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionMoveTo):
            return ActionMoveToSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionTakeTram):
            return ActionTakeTramSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionDoNotTakeTram):
            return ActionDoNotTakeTramSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionBuySquare):
            return ActionBuySquareSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionSellSquare):
            return ActionSellSquareSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionGoToJail):
            return ActionGoToJailSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionBuild):
            return ActionBuildSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionDemolish):
            return ActionDemolishSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionChooseCard):
            return ActionChooseCardSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionSurrender):
            return ActionSurrenderSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionTradeProposal):
            return ActionTradeProposalSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionTradeAnswer):
            return ActionTradeAnswerSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionMortgageSet):
            return ActionMortgageSetSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionMortgageUnset):
            return ActionMortgageUnsetSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionPayBail):
            return ActionPayBailSerializer(instance, context=self.context).data
        elif isinstance(instance, ActionBid):
            return ActionBidSerializer(instance, context=self.context).data
        
        #TODO: excepcion
        return ActionSerializer(instance, context=self.context).data

    class Meta:
        model = Action
        fields = '__all__'


def action_from_json(data, context=None):
    mapping = {
        'ActionThrowDices': ActionThrowDicesSerializer,
        'ActionMoveTo': ActionMoveToSerializer,
        'ActionTakeTram': ActionTakeTramSerializer,
        'ActionDoNotTakeTram': ActionDoNotTakeTramSerializer,
        'ActionBuySquare': ActionBuySquareSerializer,
        'ActionSellSquare': ActionSellSquareSerializer,
        'ActionGoToJail': ActionGoToJailSerializer,
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
    }
    type_name = data.get('type')
    if not type_name:
        raise serializers.ValidationError('Missing type field in action json')
    serializer_cls = mapping.get(type_name)
    if serializer_cls is None:
        raise serializers.ValidationError(f'Unknown action type: {type_name}')
    serializer = serializer_cls(data=data, context=context)
    serializer.is_valid(raise_exception=True)
    
    #model_class = serializer.Meta.model
    #instance = model_class(**serializer.validated_data)
    #return instance

    return serializer.save()


#########################################################################Fantasy stuff
class FantasyEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = FantasyEvent
        fields = ['fantasy_type','values','card_cost']

class FantasyResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = FantasyResult
        fields = ['fantasy_type','values']

######################################################################### Response serializers
class ResponseSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    class Meta:
        model = Response
        fields = ['type']
    def get_type(self, obj):
        return obj.__class__.__name__

class ResponseAuctionSerializer(ResponseSerializer):
    auction = AuctionSerializer()
    class Meta(ResponseSerializer.Meta):
        model = ResponseAuction
        fields = ResponseSerializer.Meta.fields + ['auction']

class ResponseMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResponseMovement
        fields = '__all__'


class ResponseThrowDicesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResponseThrowDices
        fields = '__all__'


class ResponseChooseSquareSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResponseChooseSquare
        fields = '__all__'

class ResponseChooseFantasySerializer(serializers.ModelSerializer):
    class Meta:
        model = ResponseChooseFantasy
        fields = '__all__'

class GeneralResponseSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        if isinstance(instance, ResponseAuction):
            return ResponseAuctionSerializer(instance, context=self.context).data
        elif isinstance(instance, ResponseMovement):
            return ResponseMovementSerializer(instance, context=self.context).data
        elif isinstance(instance, ResponseThrowDices):
            return ResponseThrowDicesSerializer(instance, context=self.context).data
        elif isinstance(instance, ResponseChooseSquare):
            return ResponseChooseSquareSerializer(instance, context=self.context).data
        elif isinstance(instance, ResponseChooseFantasy):
            return ResponseChooseFantasySerializer(instance, context=self.context).data
        else:
            return ResponseSerializer(instance, context=self.context).data
    class Meta:
        model = Response
        fields = '__all__'
