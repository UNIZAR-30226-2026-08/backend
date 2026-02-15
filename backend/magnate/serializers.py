from rest_framework import serializers
from .models import BaseSquare, PropertySquare, FantasySquare, BridgeSquare, TramSquare, ParkingSquare, ServerSquare, ExitSquare, GoToJailSquare, JailSquare


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
        fields = BaseSquareSerializer.Meta.fields + ['buy_price','build_price','rent_prices','out_successor']

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

###############################################