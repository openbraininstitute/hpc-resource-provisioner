import yaml
from pathlib import Path


class YamlLoader(yaml.SafeLoader):
    """A custom Yaml Loader for handling of includes and config values
    """

    def __init__(self, stream, config_map):
        self._root = Path(stream.name).parent
        self._config_map = config_map
        super(YamlLoader, self).__init__(stream)

    def include(self, node):
        filename = self._root / str(self.construct_scalar(node))
        with open(filename, 'r') as f:
            return YamlLoader(f, self._config_map).get_single_data()

    def config(self, node):
        config_entry = str(self.construct_scalar(node))
        return self._config_map[config_entry]


YamlLoader.add_constructor('!include', YamlLoader.include)
YamlLoader.add_constructor('!config', YamlLoader.config)


def load_yaml_extended(stream, configs):
    return YamlLoader(stream, configs).get_single_data()
