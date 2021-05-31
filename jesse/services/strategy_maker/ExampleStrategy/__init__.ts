 jesse.strategies  Strategy, cached
 jesse.indicators ta
 jesse utils


 ExampleStrategy(Strategy):
     should_long(self) -> bool:
         False

     should_short(self) -> bool:
         False

     should_cancel(self) -> bool:
         True

     go_long(self):
        pass

     go_short(self):
        pass
