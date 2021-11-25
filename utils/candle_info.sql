select (to_timestamp(min(timestamp)/1000) at time zone 'UTC')::date
        as min_date,
       (to_timestamp(max(timestamp)/1000) at time zone 'UTC')::date
        as max_date,
       count(timestamp), symbol, exchange
from candle group by exchange, symbol order by exchange, symbol;
