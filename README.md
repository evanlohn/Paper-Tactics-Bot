This repo contains the skeleton code one might want to use to write a bot that plays on the [Paper Tactics website](https://www.paper-tactics.com/)

For those interested only in writing your own bot, you can fork this repo and mostly modify `agent.py` to create a new agent subclass that implements `choose_move`. There is also some code that may be useful for forward simulation purposes in `agent_utils.py`. 

To use your own agent, after creating your class in `agent.py` you will need to modify `client.py` to import and initialize your agent in the `main()` function. 

To make the bot (whichever you select via arguments, random is default) join the paper tactics queue on the website, run `python3 client.py` from your terminal. To see the available arguments run `python3 client.py -h`. If you get an error saying websockets not found, run `python3 -m pip install -r requirements.txt`.

The best bot I have searches one turn's worth of its own moves and the other player's responses, then uses a heuristic to evaluate the resulting positions (as well as to prune the search so it isn't truly exhaustive). It can be run by cloning the repo and running the following:
`python3 client.py --agent heuristic`

If you want to avoid polluting the main paper tactics queue with your bots (highly recommended), you can add on the `code` argument:
`python3 client.py --agent heuristic --code botTest`
and then enter the code botTest into the "game code" field on the website to play against the bot.

