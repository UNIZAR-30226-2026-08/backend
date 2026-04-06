# Agent Heuristics: Probabilities and Dynamic Synergies

## 0. Core Concepts and Constants

### Required Constants
* **LANDING_PROB (PROB_CAER):** 1/54 (Probability of landing on a specific square, excluding jail).
* **TOTAL_TURNS:** 20 (Used as a baseline to calculate remaining turns).
* **AUCTION_ROI_CTE:** 0.75 (Safety margin to ensure ROI in maximum bids).
* **FANTASY_CTE:** 0.0 (Expected net value of an unknown fantasy card).

### Core Concepts
* **Expected Visits:** Landing Probability * Number of Opponents * Remaining Turns.
* **Dynamic Reserve:** The highest rent currently chargeable by any opponent on the board.
* **Rent Delta:** The gross change in rent income (including monopoly multipliers or station/bridge scaling) when gaining or losing a property.

## 1. Jail
* **EV_ExitJail:** Sum of EV of unowned buyables - Expected rent paid to others' properties - Bail cost (if applicable).
* **EV_StayInJail:** -EV_ExitJail.

## 2. Buying and Special Moves
* **Buyables (Properties/Bridges/Servers):** EV = (Rent Delta * Expected Visits) + Block Value - Buy Price.
  * *Block Value:* Evaluated ONLY if an opponent already owns properties of the same group. Weighted by the number of opponents.
* **Trams:**
  * **Take Tram:** EV = Uniform average EV of the next 12 linearly connected squares - Travel cost.
  * **Skip Tram:** EV = Uniform average EV of the next 12 linearly connected squares from the current position.

## 3. Square Selection
The square with the highest expected value is chosen.
* **Opponent's Property EV:** -Current Rent owed.

## 4. Business and Construction
* **Build:** EV = (Projected rent increase * Expected Visits) - Build price.
* **Demolish:** EV = Refund (Build price / 2) - (Rent loss * Expected Visits).
* **Unmortgage:** EV = (Rent Delta gained * Expected Visits) - Cost (Buy price / 2).
* **Mortgage:** EV = Cash gained (Buy price / 2) - (Rent Delta lost * Expected Visits).
*(Note: Rent Delta automatically factors in the monopoly multiplier impact).*

## 5. Auctions
* **Max ROI Bid:** (Square Buying EV + Buy Price) * AUCTION_ROI_CTE.
* **Budget:** Current Money - Dynamic Reserve.
* **Max Bid:** Minimum between Budget and Max ROI Bid.
* **Real Bids:** Distributed across MaxBid or 0 (not to bid).

## 6. Liquidation and Surrender
* **Liquidate:** Handled inherently by EV sorting. Demolishing/mortgaging monopolies generates massive negative EV due to the Rent Delta penalty, forcing the agent to liquidate low-value single properties first.
* **Surrender:** Executed only if there are absolutely no other actions available to raise funds.

## 7. Trades
* **EV_Trade:** Own Net Benefit - (Rival Net Benefit / Number of Opponents).
* **Net Benefit:** (Money Gained + Rent Delta Gained * Expected Visits) - (Money Lost + Rent Delta Lost * Expected Visits).
* **Propose (Initiative):** Identify target properties and generate random offers prioritizing EV_Trade > 0. Offer value is capped at 80% of the target's buying EV to ensure profitability.
* **Decision:** Accept or propose exclusively if EV_Trade > 0.