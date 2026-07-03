# Autocreaser for folding kayaks

### Motivation
We wanted to see if we could automate the creasing of polypropylene sheets when [folding kayaks.](./README.md)

We have ordered a first prototype

![First prototype](./Images/autocrease/autocreaser.jpg)

## BOM
- Ø8mm Steel spring pin QB515-SH, M16 [Aliexpress](https://www.aliexpress.com/item/1005006329455989.html)
- Conveyor Ball Roller QB312, M16 [Aliexpress](https://www.aliexpress.com/item/1005005415776359.html)
- M16 long hex nut [Aliexpress](https://www.aliexpress.com/item/1005003505777678.html)

## Working principle theory, untested

- Mount Ø8mm sping pin in spindle collet on shopbot
- Adjust the Z-offset to control the pressure on the sheet
- Have a hot air gun fixed on the contact point, set to 100-150C on a distance that doesn't overheat the plastic.

## Potential problems

- If we hit something the sideways forces may damage the spindle bearings since the tool stickout is very long. Need to be careful or 3D-print a holder that can act as a break-away if we have ha catastrophic collison.

Spring pin force

![Spring pin force](./Images/autocrease/table.jpg)

Ball size

![ball size](./Images/autocrease/ball.jpg)
