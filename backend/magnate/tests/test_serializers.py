from django.test import TestCase
from django.core.management import call_command
from magnate.models import BaseSquare
from magnate.serializers import GeneralSquareSerializer

class PropertySquareSerializerTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_boards')

    #TODO: hacer más y refinar este
    def test_1(self):
        casillas = BaseSquare.objects.all()
        print('printear')
        print(casillas[1])
        print(GeneralSquareSerializer(casillas[1]).data)
        self.assertTrue(True)