import random

class BeerGameSession:
    def __init__(self, settings):
        self.week = 1
        self.total_rounds = settings.get("semanas", 30)
        self.holding_cost = settings.get("holding_cost", 0.5)
        self.backlog_cost = settings.get("backlog_cost", 1.0)
        self.difficulty = settings.get("dificultad", "Clásico")
        self.ai_profile = settings.get("ai_profile", "Clásico")
        self.human_indices = settings.get("human_indices", [0])
        
        # Nuevos parámetros de Lead Time
        self.lt_info = settings.get("lt_info", 2)
        self.lt_material = settings.get("lt_material", 2)
        
        self.inventory = [12, 12, 12, 12] # 0 = Minorista, 1 = Mayorista, 2 = Distribuidor, 3 = Fábrica
        self.backorders = [0, 0, 0, 0]
        self.costs_accumulated = [0.0, 0.0, 0.0, 0.0]
        self.last_received = [0, 0, 0, 0]
        self.last_orders = [4, 4, 4, 4]
        self.history = []
        self.is_game_over = False

        # Init Retraso de Producto Dinámico
        self.shipments = []
        for role in range(4):
            for wl in range(1, self.lt_material + 1):
                self.shipments.append({'toRole': role, 'amount': 4, 'weeksLeft': wl})

        # Init Retraso de Información Dinámico
        self.orders_in_transit = []
        for role in range(1, 4):
            for wl in range(1, self.lt_info + 1):
                self.orders_in_transit.append({'toRole': role, 'amount': 4, 'weeksLeft': wl})

    def get_customer_demand(self):
        diff = self.difficulty
        w = self.week
        
        if "Clásico MIT" in diff:
            return 4 if w <= 4 else 8
            
        elif "Promoción Relámpago" in diff:
            if w == 8: return 24
            elif w == 9: return 12
            else: return 4
            
        elif "Crecimiento" in diff:
            if w <= 3: return 4
            elif w > 3 and w <= 15: return 4 + (w - 3) # Crece 1 por semana hasta 16
            else: return 16
            
        elif "Contracción" in diff:
            if w <= 9: return 12
            elif w == 10: return 6
            else: return 4
            
        elif "Moderada" in diff:
            return max(0, int(random.normalvariate(8, 2)))
            
        elif "Extrema" in diff:
            return max(0, int(random.normalvariate(10, 5)))
            
        else: # Default
            return 4

    def calculate_ai_order(self, role_index, new_demand):
        current_inv = self.inventory[role_index]
        current_back = self.backorders[role_index]
        on_way = sum([s['amount'] for s in self.shipments if s['toRole'] == role_index])
        
        target = 12 + (4 * self.lt_material) 
        inv_position = current_inv - current_back + on_way
        
        alpha = 0.5 
        if getattr(self, 'ai_profile', 'Clásico') == "Nervioso":
            alpha = 1.5
        elif getattr(self, 'ai_profile', 'Clásico') == "Conservador":
            alpha = 0.1
            target = 4 + (4 * self.lt_material)
            
        order = new_demand + alpha * (target - inv_position)
        
        if current_back > 0:
            if getattr(self, 'ai_profile', 'Clásico') == "Nervioso":
                order += current_back * 2.0
            elif getattr(self, 'ai_profile', 'Clásico') == "Conservador":
                order += current_back * 0.5
            else:
                order += current_back * 0.75
            
        return max(0, int(order))

    def play_turn(self, user_orders_dict):
        if self.is_game_over: return
        
        demand_customer = self.get_customer_demand()
        
        for s in self.shipments: s['weeksLeft'] -= 1
        for o in self.orders_in_transit: o['weeksLeft'] -= 1
        
        received = [0, 0, 0, 0]
        for s in self.shipments:
            if s['weeksLeft'] == 0:
                self.inventory[s['toRole']] += s['amount']
                received[s['toRole']] += s['amount']
        self.last_received = received
        self.shipments = [s for s in self.shipments if s['weeksLeft'] > 0]
        
        incoming_orders = [0, 0, 0, 0]
        incoming_orders[0] = demand_customer
        for o in self.orders_in_transit:
            if o['weeksLeft'] == 0:
                incoming_orders[o['toRole']] += o['amount']
        self.orders_in_transit = [o for o in self.orders_in_transit if o['weeksLeft'] > 0]
        
        dispatches = [0, 0, 0, 0]
        for i in range(4):
            total_req = incoming_orders[i] + self.backorders[i]
            if self.inventory[i] >= total_req:
                dispatches[i] = total_req
                self.inventory[i] -= total_req
                self.backorders[i] = 0
            else:
                dispatches[i] = self.inventory[i]
                self.backorders[i] = total_req - self.inventory[i]
                self.inventory[i] = 0
                
        # Emitir Despachos a su destino con el Lead Time Material configurado
        if dispatches[3] > 0: self.shipments.append({'toRole': 2, 'amount': dispatches[3], 'weeksLeft': max(1, self.lt_material)})
        if dispatches[2] > 0: self.shipments.append({'toRole': 1, 'amount': dispatches[2], 'weeksLeft': max(1, self.lt_material)})
        if dispatches[1] > 0: self.shipments.append({'toRole': 0, 'amount': dispatches[1], 'weeksLeft': max(1, self.lt_material)})
        
        turn_costs = [0, 0, 0, 0]
        for i in range(4):
            turn_costs[i] = (self.inventory[i] * self.holding_cost) + (self.backorders[i] * self.backlog_cost)
            self.costs_accumulated[i] += turn_costs[i]
            
        placed_orders = [0, 0, 0, 0]
        for i in range(4):
            if i in user_orders_dict:
                placed_orders[i] = user_orders_dict[i]
            else:
                placed_orders[i] = self.calculate_ai_order(i, incoming_orders[i])
                
        self.last_orders = placed_orders
        
        # Emitir Pedidos Aguas Arriba con el Lead Time Información
        if placed_orders[0] > 0: self.orders_in_transit.append({'toRole': 1, 'amount': placed_orders[0], 'weeksLeft': max(1, self.lt_info)})
        if placed_orders[1] > 0: self.orders_in_transit.append({'toRole': 2, 'amount': placed_orders[1], 'weeksLeft': max(1, self.lt_info)})
        if placed_orders[2] > 0: self.orders_in_transit.append({'toRole': 3, 'amount': placed_orders[2], 'weeksLeft': max(1, self.lt_info)})
        if placed_orders[3] > 0: self.shipments.append({'toRole': 3, 'amount': placed_orders[3], 'weeksLeft': max(1, self.lt_material)})

        self.history.append({
            "week": self.week,
            "demand": demand_customer,
            "roles": [{"inv": self.inventory[i], "back": self.backorders[i], "order": placed_orders[i], "received": received[i], "cost": turn_costs[i], "accum_cost": self.costs_accumulated[i]} for i in range(4)],
        })
        
        self.week += 1
        if self.week > self.total_rounds:
            self.is_game_over = True

            
    def get_role_diagnostics(self, role_index):
        if len(self.history) == 0:
            return {"moodEmoji": "😌", "stressors": [], "percentChange": "0"}

        current_back = self.backorders[role_index]
        last_rec = self.last_received[role_index]
        
        last_round = self.history[-1]
        prev_round = self.history[-2] if len(self.history) > 1 else None

        current_order = last_round["roles"][role_index]["order"]
        prev_order = prev_round["roles"][role_index]["order"] if prev_round else 4
        
        safe_prev = 1 if prev_order == 0 else prev_order
        percent_change = ((current_order - safe_prev) / safe_prev) * 100

        stressors = []
        moodEmoji = "😌"
        
        if abs(percent_change) > 30:
            stressors.append({"label": "Var%", "icon": "🌊"})
            if percent_change > 0: moodEmoji = "📈"

        if current_back > 0:
            stressors.append({"label": "Stock", "icon": "📉"})
            moodEmoji = "😰"

        if current_back > 10 or percent_change > 100:
            moodEmoji = "🔥"

        return {
            "moodEmoji": moodEmoji,
            "stressors": stressors,
            "percentChange": f"{percent_change:.0f}"
        }
