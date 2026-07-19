class WorldRegistry:
    """
    Holds multiple environments (different physics worlds)
    """

    def __init__(self):
        self.worlds = {}

    def add_world(self, env):
        self.worlds[env.name] = env

    def get_world(self, name):
        return self.worlds.get(name)

    def list_worlds(self):
        return list(self.worlds.keys())
