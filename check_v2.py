import discord
import inspect

print("discord.py:", discord.__version__)

print("\nLayoutView:")
print(inspect.signature(discord.ui.LayoutView))

print("\nContainer:")
print(inspect.signature(discord.ui.Container))

print("\nTextDisplay:")
print(inspect.signature(discord.ui.TextDisplay))

print("\nMediaGallery:")
print(inspect.signature(discord.ui.MediaGallery))

print("\nSeparator:")
print(inspect.signature(discord.ui.Separator))
