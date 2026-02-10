import json
from django.core.management.base import BaseCommand
from django.db import transaction
from magnate.models import * 

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        try:
            with open('boards/board1.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR("File not found!"))
            return

        
        instances_dict = {}
        successors_in = {}
        successors_out = {}

        with transaction.atomic():
            # Clean DB
            Board.objects.all().delete()
            BaseSquare.objects.all().delete()

            # Create Board
            board = Board.objects.create(custom_id=data.get('id'))
            self.stdout.write("Board created.")

            # Property squares
            for item in data.get('property_squares', []):
                fields = {'board': board}
                if 'id' in item and 'id_successor' in item: 
                    successors_in[item['id']] = item['id_successor']

                if 'group' in item: fields['group'] = item['group']
                if 'buy_price' in item: fields['buy_price'] = item['buy_price']
                if 'build_price' in item: fields['build_price'] = item['build_price']
                if 'rent_prices' in item: fields['rent_prices'] = item['rent_prices']
                if 'build_price' in item: fields['build_price'] = item['build_price']

                # Create and Cache
                instance = PropertySquare.objects.create(**fields)
                instances_dict[item['id']] = instance

            # Bridge squares
            for item in data.get('bridge_squares', []):
                fields = {'board': board}
                if 'id' in item and 'in_successor' in item: 
                    successors_in[item['id']] = item['in_successor']
                    if 'out_successor' in item:
                        successors_out[item['id']] = item['out_successor']

                if 'rent_prices' in item: fields['rent_prices'] = item['rent_prices']
                instance = BridgeSquare.objects.create(**fields)
                instances_dict[item['id']] = instance

            # Tram squares
            for item in data.get('tram_squares', []):
                fields = {'board': board}
                if 'id' in item and 'id_successor' in item: 
                    successors_in[item['id']] = item['id_successor']

                if 'buy_price' in item: fields['buy_price'] = item['buy_price']
                instance = TramSquare.objects.create(**fields)
                instances_dict[item['id']] = instance

            # Server squares
            for item in data.get('server_squares', []):
                fields = {'board': board}
                if 'id' in item and 'id_successor' in item: 
                    successors_in[item['id']] = item['id_successor']

                if 'buy_price' in item: fields['buy_price'] = item['buy_price']
                if 'rent_prices' in item: fields['rent_prices'] = item['rent_prices']
                instance = ServerSquare.objects.create(**fields)
                instances_dict[item['id']] = instance

            # Fantasy squares
            for item in data.get('fantasy_squares', []):
                fields = {'board': board}
                if 'id' in item and 'id_successor' in item: 
                    successors_in[item['id']] = item['id_successor']

                instance = FantasySquare.objects.create(**fields)
                instances_dict[item['id']] = instance

            item = data.get('exit_square', [])
            if item:
                fields = {'board': board}
                if 'id' in item and 'id_successor' in item: 
                    successors_in[item['id']] = item['id_successor']

                if 'init_money' in item: fields['init_money'] = item['init_money']
                instance = ExitSquare.objects.create(**fields)
                instances_dict[item['id']] = instance

            item = data.get('go_to_jail_square', [])
            if item:
                fields = {'board': board}
                if 'id' in item and 'id_successor' in item: 
                    successors_in[item['id']] = item['id_successor']

                instance = GoToJailSquare.objects.create(**fields)
                instances_dict[item['id']] = instance

            item = data.get('jail_square', [])
            if item:
                fields = {'board': board}
                if 'id' in item and 'id_successor' in item: 
                    successors_in[item['id']] = item['id_successor']

                if 'bail_price' in item: fields['bail_price'] = item['bail_price']
                instance = JailSquare.objects.create(**fields)
                instances_dict[item['id']] = instance

            item = data.get('parking_square', [])
            if item:
                fields = {'board': board}
                if 'id' in item and 'id_successor' in item: 
                    successors_in[item['id']] = item['id_successor']

                instance = ParkingSquare.objects.create(**fields)
                instances_dict[item['id']] = instance

            self.stdout.write(f"Pass 1 Complete: Created {len(instances_dict)} squares.")

            for sq_id, instance in instances_dict.items():
                instance.custom_id = sq_id

                if sq_id in successors_in:
                    instance.in_successor = instances_dict[successors_in[sq_id]]
                if sq_id in successors_out:
                    instance.out_successor = instances_dict[successors_out[sq_id]]

                instance.save()

            self.stdout.write(f"Pass 2 Complete: Linked squares.")

