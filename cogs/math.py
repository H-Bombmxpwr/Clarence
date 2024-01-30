import discord
from  sympy import *
from discord.ext import commands
import matplotlib.pyplot as plt
from PIL import Image
import os
import time    
from functionality.structures import Bits
from  functionality.functions import collatz
import matplotlib.pyplot as plt
import uuid

class Math(commands.Cog):
  """ 
  Math Class
  """
  def __init__(self,client):
      self.client = client
      

  @commands.command(help="LaTeX Rendering", aliases=["tex"])
  async def latex(self, ctx, *, latex_string=None):
        if latex_string is None:
            await ctx.send("Please send LaTeX code to be rendered.")
            return

        # Generate a unique file name
        png_path = f"{uuid.uuid4()}.png"

        try:
            plt.subplot(111)
            plt.axis('off')
            plt.text(0.5, 0.5, r"$%s$" % latex_string, fontsize=30, color="black", ha='center', va='center')
            plt.savefig(png_path, format="png", bbox_inches='tight', pad_inches=0.1)
            plt.clf()
            plt.close()

            await ctx.send(file=discord.File(png_path))
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
        finally:
            if os.path.exists(png_path):
                os.remove(png_path)


   
  @commands.command(help = "Binary/Hex/Decimal/Ascii converter")
  async def bits(self,ctx,typ:str = None,input = None):
       
      if typ == None:
        await ctx.send('Please specify what you are sending: `ascii` , `decimal`, `hex`, or `binary`\ni.e `bits decimal 35`')
      elif input == None:
        await ctx.send('Please add a value to convert\ni.e `bits decimal 35`')
      
      else:
        Bit = Bits(typ,input)
        decimal = Bit.to_decimal(typ[0].lower(),input)
        if decimal == None:
          await ctx.send("That is not a valid value for that type")
          return
        decimal,ascii,hexa,binary = Bit.from_decimal(decimal)
        await ctx.send("Binary: `" + str(binary) + "`\nHex: `" + str(hexa) + "`\nDecimal: `" + str(decimal) + "`\nAscii: `" + str(ascii) + "`")

  #simple collatz conjecture function
  @commands.command(help = "Run the Collatz Conjecture")
  async def collatz(self,ctx, num:int = None):
    if num == None:
      await ctx.send("Please send a postive integer as an argument")
    else:
      try:
        c = collatz(num)
      except:
        await ctx.send("Please send a postive integer")
      await ctx.send(f"Total Calculations: `{c}`")

async def setup(client):
   await client.add_cog(Math(client))

