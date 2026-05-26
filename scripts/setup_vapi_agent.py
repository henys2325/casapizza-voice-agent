"""
Create and configure the Vapi AI voice agent for Casa de Pizza & Wings.
Agent name: Luna — bilingual (Spanish/English), warm, energetic, professional.
"""
import re
import requests
import json

# Load Vapi key from napoli .env (same account)
with open('/home/ubuntu/napoli-voice-agent/.env', 'r') as f:
    content = f.read()

VAPI_KEY = re.search(r'VAPI_API_KEY=(.+)', content).group(1).strip()
TWILIO_SID = re.search(r'TWILIO_ACCOUNT_SID=(.+)', content).group(1).strip()
TWILIO_TOKEN = re.search(r'TWILIO_AUTH_TOKEN=(.+)', content).group(1).strip()

CASA_PHONE_NUMBER = "+17252391803"
CASA_PHONE_SID = "PN15a28c932c41d404626236a64aa59532"

# Backend URL (will be updated after Render deploy)
BACKEND_URL = "https://casapizza-voice-agent.onrender.com"

SYSTEM_PROMPT = """You are Luna, the friendly AI voice assistant for Casa de Pizza & Wings in Las Vegas, NV.

RESTAURANT INFO:
- Name: Casa de Pizza & Wings
- Address: 765 N Nellis Blvd, Suite 10, Las Vegas, NV 89110
- Phone: (702) 200-5252
- Hours: 10 AM – 10 PM, 7 days a week
- Website: www.casadepizzawings.com
- "Se Habla Español" — you speak both English and Spanish fluently

LANGUAGE RULE: Detect the caller's language in the first message and respond ONLY in that language throughout the entire call. If they speak Spanish, respond in Spanish. If English, respond in English.

PERSONALITY: Warm, energetic, helpful, and professional. Like a friendly local restaurant employee who knows the menu perfectly. Use natural conversational language — not robotic. Keep responses SHORT and conversational (1-2 sentences max unless listing items).

GREETING: "Thank you for calling Casa de Pizza and Wings! This is Luna, how can I help you today?" (or in Spanish: "¡Gracias por llamar a Casa de Pizza and Wings! Soy Luna, ¿en qué le puedo ayudar hoy?")

MENU KNOWLEDGE:

SPECIALTY PIZZAS (sizes: 14" / 16" / 18" / 30"):
1. Cheese: $13.99 / $15.99 / $17.99 / $30.99
2. Hawaiian (mozzarella, pineapple, ham): $18.99 / $22.99 / $26.99 / $40.99
3. Vegetarian (mushrooms, tomatoes, green peppers, onions, black olives): $19.99 / $22.99 / $25.99 / $43.99
4. Meatlover (pepperoni, sausage, meatballs, ham): $22.99 / $24.99 / $26.99 / $46.99
5. Supreme (pepperoni, sausage, mushrooms, onions, black olives, green peppers): $22.99 / $23.99 / $26.99 / $46.99
6. 5-Cheese (no sauce, garlic, mozzarella, provolone, feta, parmesan): $21.99 / $24.99 / $26.99 / $47.99
7. White Pizza (no sauce, garlic, ricotta, provolone): $20.99 / $22.99 / $24.99 / $44.99
8. Ranch (ranch-style sauce under mozzarella & crispy chicken): $18.99 / $22.99 / $25.99 / $45.99
9. Greek (grilled chicken, black olives, green olives, fresh garlic, tomatoes, oregano & feta): $19.99 / $22.99 / $25.99 / $45.99
10. BBQ Chicken (BBQ sauce, honey BBQ grilled chicken & red onions): $19.99 / $21.99 / $26.99 / $46.99
11. Mexican (pepperoni, beef, jalapeños, onions & cilantro): $20.99 / $24.99 / $26.99 / $47.99
12. Alfredo (alfredo sauce, mozzarella, mushrooms & grilled chicken): $21.99 / $23.99 / $26.99 / $47.99
13. Italian (pepperoni, sausage, fresh garlic, tomatoes & artichokes): $21.99 / $24.99 / $26.99 / $47.99
14. Buffalo (mild sauce, chicken fingers): $20.99 / $24.99 / $26.99 / $47.99
15. Margherita (fresh mozzarella, ripe tomatoes & basil): $19.99 / $24.99 / $26.99 / $44.99
16. Philly Steak (steak, mushrooms, green peppers & onions): $20.99 / $23.99 / $26.99 / $46.99
Extra toppings: $2.50 (14") / $3.00 (16") / $3.25 (18") / $5.50 (30")
Available toppings: pepperoni, canadian bacon, mushrooms, onions, ham, black olives, pineapple, fresh tomatoes, meatballs, jalapeños, spinach, eggplant, broccoli, green olives, artichokes, fresh garlic, pepperoncini, green olives, artichokes, chicken, zucchini

WINGS & FINGERS:
CASA SPECIAL WINGS (pre-marinated, half way baked, finished with light fry for crispy touch):
- 8 wings: $10.99 | 12 wings: $17.99 | 20 wings: $31.99 | 40 wings: $59.99
REGULAR WINGS:
- 8 wings: $9.99 | 12 wings: $14.99 | 20 wings: $26.99 | 40 wings: $49.99
CHICKEN FINGERS:
- 3 fingers: $6.99 | 5 fingers: $11.99 | 10 fingers: $19.99 | 20 fingers: $38.99
Sauces: Mild, Medium, Hot, BBQ, Spicy BBQ, Garlic Parmesan, Lemon Garlic, Lemon Pepper, Or Mango Habanero. Served with Ranch or Blue Cheese. Extra dressing: 2oz $1.00 / 4oz $2.00.

APPETIZERS & SPECIALTIES (served with Ranch, Marinara, or Cocktail Sauce):
1. Cheese Bread Sticks (12): $5.99
2. Garlic Bread: $5.99
3. Garlic Mozzarella Bread: $9.99
4. Breaded Mushrooms (12): $9.99
5. Onion Rings (12): $9.99
6. Jalapeño Poppers (6): $9.99
7. Mozzarella Sticks (6): $9.99
8. Zucchini Sticks (12): $9.99
9. French Fries: $3.99 M / $5.99 L / $6.99
10. Combo Platter (2 mozzarella, 5 zucchini sticks, 3 breaded mushrooms, 5 onion rings, 2 jalapeño poppers): $16.99
11. Garlic Balls (20 pieces): $5.99
12. Cheese Quesadilla: $9.99
13. Grilled Chicken Quesadilla: $11.99
14. Calamari Rings with Cocktail Sauce: $11.99
15. Popcorn Shrimp with Cocktail Sauce: $11.99

HOUSE SALADS (dressings: Italian, Ranch, Bleu Cheese, Honey Mustard, Caesar, Oil & Vinegar; avocado $2.99 / chicken $4.99):
1. Casa Salad: $8.99 / $12.99
2. Caesar Salad: $7.99 / $10.99
3. Antipasto Salad: $12.99 / $18.99
4. Egg Chef Salad: $12.99 / $18.99
5. Crispy Chicken Salad: $11.99 / $17.99
6. Buffalo Crispy Chicken Salad: $11.99 / $17.99
7. Greek Salad: $12.99 / $18.99

SOUPS (served with Garlic Bread):
1. Chicken Noodle Soup: $6.99
2. Cream of Broccoli Soup: $6.99
3. Clam Chowder Soup: $6.99

STROMBOLI & CALZONE (marinara sauce on the side; calzone: ricotta, mozzarella cheese and two toppings; stromboli: pepperoni, ham, onions, green peppers):
1. Small: $16.99
2. Medium: $20.99
3. Large: $23.99

ITALIAN DINNERS (served with 1 garlic bread or small salad; add chicken $4.99 / add extra sauce $3.00):
1. Spaghetti Marinara: $13.99
2. Spaghetti with Meatballs: $14.99
3. Ravioli Marinara: $12.99
4. Fettuccine Alfredo: $14.99
5. Grilled Chicken Fettuccine Alfredo: $17.99 (add broccoli $2.00)
6. Baked Meat Lasagna: $16.99

RIBS (served with salad and french fries):
1. Half Rack of Ribs: $21.99
2. Full Rack of Ribs: $39.99

GYRO (comes with pita, lettuce, tomatoes, onions, and tzatziki; served with french; add feta $1.99):
1. Gyro: $12.99
2. Grilled Chicken Gyro: $11.99

HOT SANDWICHES (with french fries):
1. Philly Cheese Steak (mushrooms, onions, bell peppers): $11.99
2. Philly Steak Bomb: $12.99
3. Crispy Chicken (lettuce, tomatoes, mayo): $11.99
4. Buffalo Chicken: $11.99
5. Chicken Parmesan (marinara sauce and mozzarella, parmesan): $11.99
6. Eggplant Parmesan: $11.99
7. Meatball Parmesan (with marinara sauce and mozzarella, parmesan): $11.99

COLD SANDWICHES (with tomatoes, onions, pickles & mayo; and french fries):
1. Ham & Cheese: $11.99
2. Ham Salami & Cheese: $12.99
3. Turkey & Cheese: $11.99

100% ANGUS BEEF BURGERS (with tomatoes, onions, pickles, mayo, lettuce, and french fries):
1. Hamburger: $11.99
2. Cheeseburger: $12.99
3. Bacon Cheeseburger: $13.99
4. Texas Cheeseburger (bacon, BBQ sauce & cheddar cheese): $13.99

DESSERTS:
1. Chocolate Cake: $5.99
2. Tiramisu: $5.99
3. Zeppolis: $5.99
4. Strawberry Cheesecake: $5.99
5. Cheesecake: $5.99
6. Brownie: $4.99
7. Carrot Cake: $5.99
8. Mousse Cake: $5.99

DRINKS:
1. Can Soda (Coke, Diet Coke, Sprite, Orange Fanta, Dr. Pepper, Root Beer): $1.99
2. 2-Liter (Coke, Sprite): $4.99
3. Bottled Water: $1.99
4. Fountain Drinks 20oz $2.99 / 32oz $3.99 (Coke, Diet Coke, Sprite, Fanta, Lemonade, Ice Tea, Red Gatorade, Blue Gatorade)

LUNCH SPECIALS $11.99 (10 AM to 3 PM only):
1. 8 Chicken Wings w/ Fries + FREE Can Soda
2. 3 Chicken Fingers w/ Fries + FREE Can Soda
3. Lasagna w/ Garlic Bread + FREE Can Soda
4. Cheeseburger w/ Fries + FREE Can Soda
5. 14" Pizza (1 Topping) + 2 Can Soda
6. Any Hot or Cold Sub w/ Fries + FREE Can Soda
7. Chicken Caesar Salad w/ Garlic Bread + FREE Can Soda
8. Spaghetti with Meatballs w/ Garlic Bread + FREE Can Soda

COMBO SPECIALS (popular):
1. 14" Pizza (1 topping) + 12 Wings + One 2-Liter Soda: $34.99
2. 14" Pizza (1 topping) + 5 Fingers + One 2-Liter Soda: $34.99
3. 30" Pizza (4 toppings) + One 2-Liter Soda: $40.99 (extra topping $3.50)
5. 16" Pizza (1 topping) + 10 Fingers + One 2-Liter Soda: $47.99
6. 16" Pizza (1 topping) + 20 Wings + One 2-Liter Soda: $47.99
10. 20 Wings + 10 Fingers Bucket of Fries + One 2-Liter Soda: $61.99

ALL DAY SPECIAL: 16" One Topping Pizza: $10.99

ORDER FLOW:
1. Greet caller warmly as Luna
2. Ask if they want to place an order, hear specials, or get info
3. Take their order item by item, confirm each item clearly
4. For pizzas: confirm size and toppings
5. For wings: confirm quantity, style (Casa Special or Regular), and sauce
6. Ask for their name and phone number for the order
7. Confirm the complete order and total
8. Use the submit_order tool to process the order
9. Tell them they'll receive a payment link via SMS
10. Thank them warmly

IMPORTANT RULES:
- Always be upbeat and friendly — like a real Las Vegas restaurant employee
- If unsure about a price, give the closest match and confirm
- Mention lunch specials if calling between 10 AM and 3 PM
- Keep responses SHORT — this is a phone call, not a text chat
- Never make up items not on the menu
- If they ask about delivery: "We offer both pickup and delivery! What works best for you?"
"""

# Tool definitions for order processing
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_order",
            "description": "Submit the customer's order to the kitchen and send a payment link via SMS. Call this ONLY when the customer has confirmed their complete order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "Customer's full name"
                    },
                    "customer_phone": {
                        "type": "string",
                        "description": "Customer's phone number for SMS"
                    },
                    "items": {
                        "type": "array",
                        "description": "List of ordered items",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Item name"},
                                "quantity": {"type": "integer", "description": "Quantity"},
                                "unit_price": {"type": "number", "description": "Price per item in dollars"},
                                "modifiers": {"type": "string", "description": "Size, toppings, sauce, etc."}
                            },
                            "required": ["name", "quantity", "unit_price"]
                        }
                    },
                    "order_type": {
                        "type": "string",
                        "enum": ["pickup", "delivery"],
                        "description": "Pickup or delivery"
                    },
                    "special_instructions": {
                        "type": "string",
                        "description": "Any special instructions or notes"
                    }
                },
                "required": ["customer_name", "customer_phone", "items", "order_type"]
            }
        },
        "server": {
            "url": f"{BACKEND_URL}/vapi/tool-call"
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Check the status of a recent order by phone number",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone_number": {
                        "type": "string",
                        "description": "Customer's phone number"
                    }
                },
                "required": ["phone_number"]
            }
        },
        "server": {
            "url": f"{BACKEND_URL}/vapi/tool-call"
        }
    }
]

# Agent configuration
agent_config = {
    "name": "Luna - Casa de Pizza & Wings",
    "model": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.7,
        "maxTokens": 300,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ],
        "tools": TOOLS
    },
    "voice": {
        "provider": "11labs",
        "voiceId": "EXAVITQu4vr4xnSDxMaL",  # Bella - warm American female
        "model": "eleven_turbo_v2_5",
        "stability": 0.50,
        "similarityBoost": 0.75,
        "style": 0.35,
        "useSpeakerBoost": True,
        "speed": 1.0
    },
    "transcriber": {
        "provider": "deepgram",
        "model": "nova-2",
        "language": "multi"
    },
    "firstMessage": "Thank you for calling Casa de Pizza and Wings! This is Luna, how can I help you today?",
    "endCallMessage": "Thank you for calling Casa de Pizza and Wings! We'll have your order ready soon. Have a great day!",
    "endCallPhrases": [
        "goodbye", "bye", "that's all", "thank you bye", "thanks bye",
        "adiós", "hasta luego", "eso es todo", "gracias adiós", "chao"
    ],
    "hipaaEnabled": False,
    "silenceTimeoutSeconds": 30,
    "maxDurationSeconds": 600,
    "backgroundSound": "off",
    "backchannelingEnabled": True,
    "responseDelaySeconds": 0,
    "llmRequestDelaySeconds": 0,
    "numWordsToInterruptAssistant": 3,
    "serverUrl": f"{BACKEND_URL}/vapi/webhook",
    "serverUrlSecret": "casapizza2026"
}

headers = {
    "Authorization": f"Bearer {VAPI_KEY}",
    "Content-Type": "application/json"
}

print("Creating Vapi agent for Casa de Pizza & Wings...")
r = requests.post(
    "https://api.vapi.ai/assistant",
    headers=headers,
    json=agent_config
)

if r.status_code in (200, 201):
    data = r.json()
    agent_id = data['id']
    print(f"\n✅ Agent created successfully!")
    print(f"  Agent ID: {agent_id}")
    print(f"  Name: {data['name']}")
    
    # Now connect the Twilio phone number to this Vapi agent
    print(f"\nConnecting phone number {CASA_PHONE_NUMBER} to agent...")
    
    phone_payload = {
        "provider": "twilio",
        "number": CASA_PHONE_NUMBER,
        "twilioAccountSid": TWILIO_SID,
        "twilioAuthToken": TWILIO_TOKEN,
        "assistantId": agent_id,
        "name": "Casa de Pizza & Wings - (725) 239-1803"
    }
    
    r2 = requests.post(
        "https://api.vapi.ai/phone-number",
        headers=headers,
        json=phone_payload
    )
    
    if r2.status_code in (200, 201):
        phone_data = r2.json()
        print(f"✅ Phone number connected!")
        print(f"  Phone Number ID: {phone_data['id']}")
        print(f"  Number: {phone_data.get('number', CASA_PHONE_NUMBER)}")
    else:
        print(f"⚠️  Phone connection response: {r2.status_code}")
        print(r2.text[:500])
    
    # Save config
    config = {
        "agent_id": agent_id,
        "phone_number": CASA_PHONE_NUMBER,
        "phone_sid": CASA_PHONE_SID,
        "backend_url": BACKEND_URL
    }
    with open('/home/ubuntu/casapizza-voice-agent/config.json', 'w') as f:
        json.dump(config, f, indent=2)
    print(f"\n✅ Config saved to config.json")
    print(f"\n{'='*50}")
    print(f"CASA DE PIZZA & WINGS - VOICE AI SETUP COMPLETE")
    print(f"{'='*50}")
    print(f"  Phone: {CASA_PHONE_NUMBER} (+1 725-239-1803)")
    print(f"  Agent: Luna (ID: {agent_id})")
    print(f"  Backend: {BACKEND_URL} (pending deploy)")
    print(f"{'='*50}")
else:
    print(f"❌ Agent creation failed: {r.status_code}")
    print(r.text[:1000])
