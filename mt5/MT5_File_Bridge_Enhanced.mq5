//+------------------------------------------------------------------+
//|                MT5_File_Bridge_Enhanced.mq5                      |
//|   Enhanced file-based bridge for Python-MT5 integration         |
//|   Supports buy/sell/modify/close commands & full state export   |
//+------------------------------------------------------------------+
#property copyright "Artan Ahmadi - Enhanced v4"
#property version   "4.00"

input string TradingSymbol = "XAUUSD";
input int    WriteIntervalSec = 1;
input double DefaultLotSize = 0.01;
input bool   EnableTrading = true;
input bool   DetailedLogging = true;

// === ATR-based SL/TP inputs ======================================
input bool   UseATRBasedSLTP     = true;         // enable ATR-based SL/TP when missing
input ENUM_TIMEFRAMES ATR_TF     = PERIOD_M15;   // ATR timeframe
input int    ATR_Period          = 14;           // ATR period
input double ATR_SL_Multiplier   = 1.5;          // SL = ATR * this
input double ATR_TP_Multiplier   = 3.0;          // TP = ATR * this (ignored if RR>0)
input double ATR_RR_Override     = 0.0;          // If >0, TP = SL * RR (e.g., 2.0)
// ================================================================

datetime last_write = 0;
datetime last_account_write = 0;
datetime last_trades_write = 0;
datetime last_positions_write = 0;

// NEW writers cadence
datetime last_orders_write     = 0;
datetime last_tick_write       = 0;
datetime last_symbolinfo_write = 0;
datetime last_orderbook_write  = 0;
datetime last_rates_write      = 0;

//+------------------------------------------------------------------+
//| Trade command structure                                          |
//+------------------------------------------------------------------+
struct TradeCommand
{
   string   action;       // "buy", "sell", "modify", or "close"
   string   symbol;       // Trading symbol
   double   lot_size;     // Position size
   double   stop_loss;    // Stop loss price
   double   take_profit;  // Take profit price
   string   comment;      // Order comment
   int      magic_number; // Magic number
   string   trade_id;     // Unique trade ID (added)
   long     ticket;       // Position ticket (for modify/close)
    double   close_volume; // Partial close volume (lots). If 0, close full volume
};

//+------------------------------------------------------------------+
//| Utility: trading allowed?                                        |
//+------------------------------------------------------------------+
bool IsTradeAllowedFunc()
{
   return (MQLInfoInteger(MQL_TRADE_ALLOWED) && TerminalInfoInteger(TERMINAL_TRADE_ALLOWED));
}

//+------------------------------------------------------------------+
//| OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("Enhanced MT5 File Bridge v4.0 started for symbol: ", TradingSymbol);
   Print("Auto trading enabled: ", IsTradeAllowedFunc());
   Print("Default lot size: ", DoubleToString(DefaultLotSize,2));
   EventSetTimer(1);

   // Write static symbol info at startup
   WriteSymbolInfo(TradingSymbol);

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| OnDeinit                                                         |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("Enhanced MT5 File Bridge stopped. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| OnTimer                                                          |
//+------------------------------------------------------------------+
void OnTimer()
{
   // Existing writers
   if(TimeCurrent() - last_write >= WriteIntervalSec) { WritePriceData(); last_write = TimeCurrent(); }
   if(TimeCurrent() - last_account_write >= 2)        { WriteAccountInfo(); last_account_write = TimeCurrent(); }
   if(TimeCurrent() - last_positions_write >= 2)      { WritePositions(); last_positions_write = TimeCurrent(); }
   if(TimeCurrent() - last_trades_write >= 10)        { WriteClosedTrades(); last_trades_write = TimeCurrent(); }

   // NEW: richer state
   if(TimeCurrent() - last_tick_write >= 1)           { WriteTickData(); last_tick_write = TimeCurrent(); }
   if(TimeCurrent() - last_orders_write >= 2)         { WritePendingOrders(); last_orders_write = TimeCurrent(); }
   if(TimeCurrent() - last_orderbook_write >= 2)      { WriteOrderBook(); last_orderbook_write = TimeCurrent(); }
   if(TimeCurrent() - last_rates_write >= 10)         { WriteRatesM1(TradingSymbol, 200); last_rates_write = TimeCurrent(); }
   // re-dump symbol specs every 1h (in case of broker changes)
   if(TimeCurrent() - last_symbolinfo_write >= 3600)  { WriteSymbolInfo(TradingSymbol); last_symbolinfo_write = TimeCurrent(); }

   // Command processor
   if(EnableTrading && IsTradeAllowedFunc())
      CheckTradeCommands();
}

//+------------------------------------------------------------------+
//| Write price data (basic snapshot)                                |
//+------------------------------------------------------------------+
void WritePriceData()
{
   double bid = SymbolInfoDouble(TradingSymbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(TradingSymbol, SYMBOL_ASK);
   long   volume = SymbolInfoInteger(TradingSymbol, SYMBOL_VOLUME);
   datetime t = TimeCurrent();

   string json = "{";
   json += "\"symbol\":\"" + TradingSymbol + "\",";
   json += "\"bid\":" + DoubleToString(bid, 5) + ",";
   json += "\"ask\":" + DoubleToString(ask, 5) + ",";
   json += "\"volume\":" + IntegerToString(volume) + ",";
   json += "\"timestamp\":" + IntegerToString(t) + ",";
   json += "\"server_time\":\"" + TimeToString(t) + "\"";
   json += "}";

   int handle = FileOpen(TradingSymbol + "_price.json", FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(handle != INVALID_HANDLE)
   {
      FileWrite(handle, json);
      FileClose(handle);
   }
}

//+------------------------------------------------------------------+
//| NEW: Full tick snapshot                                          |
//+------------------------------------------------------------------+
void WriteTickData()
{
   MqlTick tick;
   if(!SymbolInfoTick(TradingSymbol, tick)) return;

   double spread = 0.0;
   if(tick.ask > 0 && tick.bid > 0) spread = tick.ask - tick.bid;

   string json = "{";
   json += "\"symbol\":\""+TradingSymbol+"\",";
   json += "\"bid\":"+DoubleToString(tick.bid, 5)+",";
   json += "\"ask\":"+DoubleToString(tick.ask, 5)+",";
   json += "\"last\":"+DoubleToString(tick.last, 5)+",";
   json += "\"volume_real\":"+DoubleToString(tick.volume_real, 2)+",";
   json += "\"spread\":"+DoubleToString(spread, 5)+",";
   json += "\"time\":"+IntegerToString((long)tick.time)+",";
   json += "\"time_msc\":"+IntegerToString((long)tick.time_msc)+",";
   json += "\"flags\":"+IntegerToString((int)tick.flags);
   json += "}";

   int h = FileOpen(TradingSymbol + "_tick.json", FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h!=INVALID_HANDLE){ FileWrite(h, json); FileClose(h); }
}

//+------------------------------------------------------------------+
//| NEW: Symbol/contract specs (static)                              |
//+------------------------------------------------------------------+
void WriteSymbolInfo(string sym)
{
   string j="{";
   j+="\"symbol\":\""+sym+"\",";
   j+="\"digits\":"          + IntegerToString((int)SymbolInfoInteger(sym, SYMBOL_DIGITS)) + ",";
   j+="\"point\":"           + DoubleToString(SymbolInfoDouble(sym, SYMBOL_POINT), 8) + ",";
   j+="\"contract_size\":"   + DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE), 2) + ",";
   j+="\"volume_min\":"      + DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), 2) + ",";
   j+="\"volume_max\":"      + DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX), 2) + ",";
   j+="\"volume_step\":"     + DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP), 2) + ",";
   j+="\"tick_size\":"       + DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE), 8) + ",";
   j+="\"tick_value\":"      + DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE), 5) + ",";
   j+="\"stops_level\":"     + IntegerToString((int)SymbolInfoInteger(sym, SYMBOL_STOPS_LEVEL)) + ",";
   j+="\"freeze_level\":"    + IntegerToString((int)SymbolInfoInteger(sym, SYMBOL_FREEZE_LEVEL)) + ",";
   j+="\"swap_type\":"       + IntegerToString((int)SymbolInfoInteger(sym, SYMBOL_SWAP_TYPE)) + ",";
   j+="\"swap_long\":"       + DoubleToString(SymbolInfoDouble(sym, SYMBOL_SWAP_LONG), 5) + ",";
   j+="\"swap_short\":"      + DoubleToString(SymbolInfoDouble(sym, SYMBOL_SWAP_SHORT), 5) + ",";
   j+="\"trade_mode\":"      + IntegerToString((int)SymbolInfoInteger(sym, SYMBOL_TRADE_MODE));
   j+="}";
   int h=FileOpen("symbol_info.json", FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h!=INVALID_HANDLE){ FileWrite(h, j); FileClose(h); }
}

//+------------------------------------------------------------------+
//| Enriched account information                                     |
//+------------------------------------------------------------------+
void WriteAccountInfo()
{
   double balance      = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity       = AccountInfoDouble(ACCOUNT_EQUITY);
   double margin       = AccountInfoDouble(ACCOUNT_MARGIN);
   double free_margin  = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double profit       = AccountInfoDouble(ACCOUNT_PROFIT);
   long   leverage     = AccountInfoInteger(ACCOUNT_LEVERAGE);
   string currency     = AccountInfoString(ACCOUNT_CURRENCY);

   long   login        = (long)AccountInfoInteger(ACCOUNT_LOGIN);
   string name         = AccountInfoString(ACCOUNT_NAME);
   string server       = AccountInfoString(ACCOUNT_SERVER);
   string company      = AccountInfoString(ACCOUNT_COMPANY);
   double credit       = AccountInfoDouble(ACCOUNT_CREDIT);
   long   trade_mode   = (long)AccountInfoInteger(ACCOUNT_TRADE_MODE);

   bool   connected    = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   long   ping_last    = (long)TerminalInfoInteger(TERMINAL_PING_LAST);
   long   build        = (long)TerminalInfoInteger(TERMINAL_BUILD);

   datetime t = TimeCurrent();

   string json = "{";
   json += "\"login\":"+IntegerToString(login)+",";
   json += "\"name\":\""+name+"\",";
   json += "\"server\":\""+server+"\",";
   json += "\"company\":\""+company+"\",";
   json += "\"currency\":\""+currency+"\",";
   json += "\"leverage\":"+IntegerToString((int)leverage)+",";
   json += "\"trade_mode\":"+IntegerToString((int)trade_mode)+",";

   json += "\"balance\":"+DoubleToString(balance,2)+",";
   json += "\"equity\":"+DoubleToString(equity,2)+",";
   json += "\"margin\":"+DoubleToString(margin,2)+",";
   json += "\"free_margin\":"+DoubleToString(free_margin,2)+",";
   json += "\"profit\":"+DoubleToString(profit,2)+",";
   json += "\"credit\":"+DoubleToString(credit,2)+",";

   json += "\"terminal_connected\":"+(connected?"true":"false")+",";
   json += "\"terminal_ping_ms\":"+IntegerToString((int)ping_last)+",";
   json += "\"terminal_build\":"+IntegerToString((int)build)+",";

   json += "\"timestamp\":"+IntegerToString(t)+",";
   json += "\"server_time\":\""+TimeToString(t)+"\"";
   json += "}";

   int handle = FileOpen("account_info.json", FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(handle != INVALID_HANDLE){ FileWrite(handle, json); FileClose(handle); }
}

//+------------------------------------------------------------------+
//| Positions                                                        |
//+------------------------------------------------------------------+
void WritePositions()
{
   string json = "{";
   json += "\"timestamp\":" + IntegerToString(TimeCurrent()) + ",";
   json += "\"positions\":[";
   
   int positions_count = 0;
   int total_positions = PositionsTotal();
   
   for(int i = 0; i < total_positions; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket <= 0) continue;
      
      if(PositionSelectByTicket(ticket))
      {
         string symbol = PositionGetString(POSITION_SYMBOL);
         long type = PositionGetInteger(POSITION_TYPE);
         double volume = PositionGetDouble(POSITION_VOLUME);
         double price_open = PositionGetDouble(POSITION_PRICE_OPEN);
         double price_current = PositionGetDouble(POSITION_PRICE_CURRENT);
         double sl = PositionGetDouble(POSITION_SL);
         double tp = PositionGetDouble(POSITION_TP);
         double profit = PositionGetDouble(POSITION_PROFIT);
         double swap = PositionGetDouble(POSITION_SWAP);
         long magic = PositionGetInteger(POSITION_MAGIC);
         string comment = PositionGetString(POSITION_COMMENT);
         datetime time_open = (datetime)PositionGetInteger(POSITION_TIME);
         
         if(positions_count > 0) json += ",";
         
         json += "{";
         json += "\"ticket\":" + IntegerToString((long)ticket) + ",";
         json += "\"symbol\":\"" + symbol + "\",";
         json += "\"type\":\"" + (type == POSITION_TYPE_BUY ? "buy" : "sell") + "\",";
         json += "\"volume\":" + DoubleToString(volume, 2) + ",";
         json += "\"price_open\":" + DoubleToString(price_open, 5) + ",";
         json += "\"price_current\":" + DoubleToString(price_current, 5) + ",";
         json += "\"sl\":" + DoubleToString(sl, 5) + ",";
         json += "\"tp\":" + DoubleToString(tp, 5) + ",";
         json += "\"profit\":" + DoubleToString(profit, 2) + ",";
         json += "\"swap\":" + DoubleToString(swap, 2) + ",";
         json += "\"magic\":" + IntegerToString((int)magic) + ",";
         json += "\"comment\":\"" + comment + "\",";
         json += "\"time_open\":\"" + TimeToString(time_open) + "\",";
         json += "\"time_open_timestamp\":" + IntegerToString(time_open);
         json += "}";
         
         positions_count++;
      }
   }
   
   json += "]";
   json += "}";
   
   int handle = FileOpen("positions.json", FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(handle != INVALID_HANDLE)
   {
      FileWrite(handle, json);
      FileClose(handle);
      if(DetailedLogging && positions_count > 0)
         Print("Updated positions file with ", positions_count, " open positions");
   }
}

//+------------------------------------------------------------------+
//| Closed trades history                                            |
//+------------------------------------------------------------------+
void WriteClosedTrades()
{
   datetime from = TimeCurrent() - (30 * 24 * 3600); // Last 30 days
   datetime to = TimeCurrent() + 3600; // 1h buffer
   HistorySelect(0, TimeCurrent());
   Sleep(100);
   if(!HistorySelect(from, to))
   {
      if(DetailedLogging) Print("Failed to select history for period");
      return;
   }
   
   string json = "{";
   json += "\"timestamp\":" + IntegerToString(TimeCurrent()) + ",";
   json += "\"trades\":[";
   
   int total_deals = HistoryDealsTotal();
   int exported_count = 0;
   
   for(int i = total_deals - 1; i >= 0; i--)
   {
      ulong deal_ticket = HistoryDealGetTicket(i);
      if(deal_ticket <= 0) continue;
      long deal_entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
      if(deal_entry != DEAL_ENTRY_OUT) continue; // only exits
      
      string symbol = HistoryDealGetString(deal_ticket, DEAL_SYMBOL);
      long deal_type = HistoryDealGetInteger(deal_ticket, DEAL_TYPE);
      double volume = HistoryDealGetDouble(deal_ticket, DEAL_VOLUME);
      double price = HistoryDealGetDouble(deal_ticket, DEAL_PRICE);
      double profit = HistoryDealGetDouble(deal_ticket, DEAL_PROFIT);
      double swap = HistoryDealGetDouble(deal_ticket, DEAL_SWAP);
      double commission = HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION);
      datetime deal_time = (datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME);
      long position_id = HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID);
      string comment = HistoryDealGetString(deal_ticket, DEAL_COMMENT);

      double entry_price = 0;
      double sl = 0;
      double tp = 0;
      double total_position_profit = 0;
      double total_position_swap = 0;
      double total_position_commission = 0;
      
      for(int j = 0; j < total_deals; j++)
      {
         ulong related_ticket = HistoryDealGetTicket(j);
         if(related_ticket <= 0) continue;
         long related_position_id = HistoryDealGetInteger(related_ticket, DEAL_POSITION_ID);
         long related_entry = HistoryDealGetInteger(related_ticket, DEAL_ENTRY);
         if(related_position_id == position_id)
         {
            if(related_entry == DEAL_ENTRY_IN)
               entry_price = HistoryDealGetDouble(related_ticket, DEAL_PRICE);
            total_position_profit += HistoryDealGetDouble(related_ticket, DEAL_PROFIT);
            total_position_swap += HistoryDealGetDouble(related_ticket, DEAL_SWAP);
            total_position_commission += HistoryDealGetDouble(related_ticket, DEAL_COMMISSION);
         }
      }
      
      if(HistoryOrdersTotal() > 0)
      {
         for(int k = 0; k < HistoryOrdersTotal(); k++)
         {
            ulong order_ticket = HistoryOrderGetTicket(k);
            if(order_ticket <= 0) continue;
            long order_position_id = HistoryOrderGetInteger(order_ticket, ORDER_POSITION_ID);
            if(order_position_id == position_id)
            {
               sl = HistoryOrderGetDouble(order_ticket, ORDER_SL);
               tp = HistoryOrderGetDouble(order_ticket, ORDER_TP);
               string order_comment = HistoryOrderGetString(order_ticket, ORDER_COMMENT);
               if(StringLen(order_comment) > 0 && order_comment != "")
               {
                  if(StringFind(order_comment, "[sl") < 0 && StringFind(order_comment, "[tp") < 0)
                     comment = order_comment;
               }
               break;
            }
         }
      }
      
      double change_percent = 0;
      if(entry_price > 0)
      {
         if(deal_type == DEAL_TYPE_BUY) change_percent = ((price - entry_price) / entry_price) * 100.0;
         else                            change_percent = ((entry_price - price) / entry_price) * 100.0;
      }
      
      if(json != "{\"timestamp\":" + IntegerToString(TimeCurrent()) + ",\"trades\":[")
         json += ",";
      
      json += "{";
      json += "\"ticket\":" + IntegerToString((long)deal_ticket) + ",";
      json += "\"symbol\":\"" + symbol + "\",";
      json += "\"type\":\"" + (deal_type == DEAL_TYPE_BUY ? "buy" : "sell") + "\",";
      json += "\"volume\":" + DoubleToString(volume, 2) + ",";
      json += "\"entry_price\":" + DoubleToString(entry_price, 5) + ",";
      json += "\"exit_price\":" + DoubleToString(price, 5) + ",";
      json += "\"sl\":" + DoubleToString(sl, 5) + ",";
      json += "\"tp\":" + DoubleToString(tp, 5) + ",";
      json += "\"profit\":" + DoubleToString(total_position_profit + total_position_swap + total_position_commission, 2) + ",";
      json += "\"change_percent\":" + DoubleToString(change_percent, 2) + ",";
      json += "\"comment\":\"" + comment + "\",";
      json += "\"close_time\":\"" + TimeToString(deal_time) + "\",";
      json += "\"close_timestamp\":" + IntegerToString(deal_time);
      json += "}";
      
      exported_count++;
   }
   
   json += "]";
   json += "}";
   
   int handle = FileOpen("closed_trades.json", FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(handle != INVALID_HANDLE)
   {
      FileWrite(handle, json);
      FileClose(handle);
      if(DetailedLogging) Print("Updated closed trades file: ", exported_count, " trades exported from ", total_deals, " total deals");
   }
   else if(DetailedLogging) { Print("Failed to open closed_trades.json for writing"); }
}

//+------------------------------------------------------------------+
//| NEW: Pending orders                                              |
//+------------------------------------------------------------------+
void WritePendingOrders()
{
   string j = "{\"timestamp\":"+IntegerToString(TimeCurrent())+",\"orders\":[";
   int n = 0;
   for(int i=0;i<OrdersTotal();i++)
   {
      ulong t = OrderGetTicket(i);
      if(t==0) continue;
      if(n++) j+=",";
      j+="{\"ticket\":"+IntegerToString((long)t)
        +",\"symbol\":\""+OrderGetString(ORDER_SYMBOL)+"\""
        +",\"type\":"+IntegerToString((int)OrderGetInteger(ORDER_TYPE))
        +",\"price\":"+DoubleToString(OrderGetDouble(ORDER_PRICE_OPEN),5)
        +",\"sl\":"+DoubleToString(OrderGetDouble(ORDER_SL),5)
        +",\"tp\":"+DoubleToString(OrderGetDouble(ORDER_TP),5)
        +",\"volume\":"+DoubleToString(OrderGetDouble(ORDER_VOLUME_CURRENT),2)
        +",\"time_setup\":\""+TimeToString((datetime)OrderGetInteger(ORDER_TIME_SETUP))+"\""
        +",\"time_expiration\":\""+TimeToString((datetime)OrderGetInteger(ORDER_TIME_EXPIRATION))+"\""
        +",\"magic\":"+IntegerToString((int)OrderGetInteger(ORDER_MAGIC))
        +",\"comment\":\""+OrderGetString(ORDER_COMMENT)+"\"}";
   }
   j+="]}";
   int h=FileOpen("orders.json", FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h!=INVALID_HANDLE){ FileWrite(h, j); FileClose(h); }
}

//+------------------------------------------------------------------+
//| NEW: Order book (Depth of Market)                                |
//+------------------------------------------------------------------+
void WriteOrderBook()
{
   if(!MarketBookAdd(TradingSymbol)) return;

   MqlBookInfo bi[];
   if(MarketBookGet(TradingSymbol, bi))
   {
      string j = "{\"timestamp\":"+IntegerToString(TimeCurrent())+",\"levels\":[";
      for(int i=0;i<ArraySize(bi);i++)
      {
         if(i) j+=",";
         j+="{\"type\":"+IntegerToString((int)bi[i].type)
           +",\"price\":"+DoubleToString(bi[i].price,5)
           +",\"volume\":"+DoubleToString(bi[i].volume,2)+"}";
      }
      j+="]}";
      int h=FileOpen(TradingSymbol + "_orderbook.json", FILE_WRITE|FILE_TXT|FILE_ANSI);
      if(h!=INVALID_HANDLE){ FileWrite(h, j); FileClose(h); }
   }

   MarketBookRelease(TradingSymbol);
}

//+------------------------------------------------------------------+
//| NEW: Compact OHLCV history (M1)                                  |
//+------------------------------------------------------------------+
void WriteRatesM1(string sym, int count)
{
   MqlRates rates[];
   int copied = CopyRates(sym, PERIOD_M1, 0, count, rates);
   if(copied<=0) return;

   ArraySetAsSeries(rates, true);
   string j = "{\"symbol\":\""+sym+"\",\"timeframe\":\"M1\",\"bars\":[";
   for(int i=copied-1;i>=0;i--)  // oldest -> newest
   {
      if(i != copied-1) j+=",";
      j+="{\"t\":"+IntegerToString((long)rates[i].time)
        +",\"o\":"+DoubleToString(rates[i].open,5)
        +",\"h\":"+DoubleToString(rates[i].high,5)
        +",\"l\":"+DoubleToString(rates[i].low,5)
        +",\"c\":"+DoubleToString(rates[i].close,5)
        +",\"tv\":"+IntegerToString((long)rates[i].tick_volume)
        +",\"rv\":"+IntegerToString((long)rates[i].real_volume)
        +",\"spr\":"+IntegerToString((int)rates[i].spread)+"}";
   }
   j+="]}";

   int h=FileOpen("rates_M1.json", FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h!=INVALID_HANDLE){ FileWrite(h, j); FileClose(h); }
}

// --------------------------- JSON helpers -------------------------
string ExtractStringValue(string json, string key)
{
   string search = "\"" + key + "\":\"";
   int start = StringFind(json, search);
   if(start < 0) return "";
   start += StringLen(search);
   int end = StringFind(json, "\"", start);
   if(end < 0) return "";
   return StringSubstr(json, start, end - start);
}

double ExtractDoubleValue(string json, string key)
{
   string search = "\"" + key + "\":";
   int start = StringFind(json, search);
   if(start < 0) return 0;
   start += StringLen(search);
   int end = StringFind(json, ",", start);
   if(end < 0) end = StringFind(json, "}", start);
   if(end < 0) return 0;
   string value = StringSubstr(json, start, end - start);
   StringReplace(value, " ", "");
   return StringToDouble(value);
}

long ExtractLongValue(string json, string key)
{
   string search = "\"" + key + "\":";
   int start = StringFind(json, search);
   if(start < 0) return 0;
   start += StringLen(search);
   int end = StringFind(json, ",", start);
   if(end < 0) end = StringFind(json, "}", start);
   if(end < 0) return 0;
   string value = StringSubstr(json, start, end - start);
   StringReplace(value, " ", "");
   return StringToInteger(value);
}

// --------------------------- ATR helpers --------------------------
double RoundToTick(string sym, double price)
{
   double tick = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0.0) tick = SymbolInfoDouble(sym, SYMBOL_POINT);
   return (MathRound(price / tick) * tick);
}

bool EnforceStopsLevel(string sym, double &sl, double &tp, double open_price, bool is_buy)
{
   int    digits      = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double tick        = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0.0) tick = SymbolInfoDouble(sym, SYMBOL_POINT);
   int    stops_level = (int)SymbolInfoInteger(sym, SYMBOL_STOPS_LEVEL);
   double min_dist    = stops_level * tick;

   bool ok = true;

   if(is_buy)
   {
      if(sl > 0 && (open_price - sl) < min_dist) { sl = open_price - min_dist; ok = false; }
      if(tp > 0 && (tp - open_price) < min_dist) { tp = open_price + min_dist; ok = false; }
   }
   else
   {
      if(sl > 0 && (sl - open_price) < min_dist) { sl = open_price + min_dist; ok = false; }
      if(tp > 0 && (open_price - tp) < min_dist) { tp = open_price - min_dist; ok = false; }
   }

   if(sl > 0) sl = NormalizeDouble(RoundToTick(sym, sl), digits);
   if(tp > 0) tp = NormalizeDouble(RoundToTick(sym, tp), digits);
   return ok;
}

bool GetATR(string sym, ENUM_TIMEFRAMES tf, int period, double &atr_out)
{
   atr_out = 0.0;
   int handle = iATR(sym, tf, period);
   if(handle == INVALID_HANDLE) return false;

   double buf[];
   int copied = CopyBuffer(handle, 0, 0, 2, buf); // latest two values
   if(copied <= 0) { IndicatorRelease(handle); return false; }

   atr_out = buf[0]; // price units
   IndicatorRelease(handle);
   return (atr_out > 0.0);
}

void ComputeATRSltp(string sym, bool is_buy, double open_price, double &sl, double &tp)
{
   double atr=0.0;
   if(!GetATR(sym, ATR_TF, ATR_Period, atr)) return;

   double sl_dist = atr * ATR_SL_Multiplier;
   double tp_dist = 0.0;

   if(ATR_RR_Override > 0.0)         tp_dist = sl_dist * ATR_RR_Override;
   else if(ATR_TP_Multiplier > 0.0)  tp_dist = atr * ATR_TP_Multiplier;

   if(is_buy)
   {
      if(sl <= 0) sl = open_price - sl_dist;
      if(tp <= 0 && tp_dist > 0) tp = open_price + tp_dist;
   }
   else
   {
      if(sl <= 0) sl = open_price + sl_dist;
      if(tp <= 0 && tp_dist > 0) tp = open_price - tp_dist;
   }

   EnforceStopsLevel(sym, sl, tp, open_price, is_buy);
}

// --------------------------- Trading core -------------------------
bool ParseTradeCommand(string json, TradeCommand &cmd)
{
   cmd.action = ExtractStringValue(json, "action");
   cmd.symbol = ExtractStringValue(json, "symbol");
   cmd.lot_size = ExtractDoubleValue(json, "lot_size");
   cmd.stop_loss = ExtractDoubleValue(json, "stop_loss");
   cmd.take_profit = ExtractDoubleValue(json, "take_profit");
   cmd.comment = ExtractStringValue(json, "comment");
   cmd.magic_number = (int)ExtractDoubleValue(json, "magic_number");
   cmd.trade_id = ExtractStringValue(json, "trade_id");
   cmd.ticket = ExtractLongValue(json, "ticket");
   cmd.close_volume = ExtractDoubleValue(json, "close_volume");

   if(cmd.action != "buy" && cmd.action != "sell" && cmd.action != "modify" && cmd.action != "close")
      return false;

   if(cmd.action == "buy" || cmd.action == "sell")
   {
      if(cmd.lot_size <= 0) cmd.lot_size = DefaultLotSize;
      if(cmd.symbol == "")  cmd.symbol = TradingSymbol;
      if(cmd.trade_id == "") cmd.trade_id = IntegerToString(TimeCurrent());
   }

   if(cmd.action == "modify" || cmd.action == "close")
   {
      if(cmd.ticket <= 0) { Print("Error: ticket required for ", cmd.action, " command"); return false; }
   }
   return true;
}

bool ExecuteBuySellCommand(TradeCommand &cmd)
{
   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req); ZeroMemory(res);

   req.symbol       = cmd.symbol;
   req.volume       = NormalizeDouble(cmd.lot_size, 2);
   req.type_filling = ORDER_FILLING_IOC;
   req.deviation    = 50;
   req.magic        = cmd.magic_number;
   req.comment      = cmd.comment;
   req.action       = TRADE_ACTION_DEAL;

   int digits = (int)SymbolInfoInteger(cmd.symbol, SYMBOL_DIGITS);

   if(cmd.action == "buy")
   {
      req.type  = ORDER_TYPE_BUY;
      req.price = SymbolInfoDouble(cmd.symbol, SYMBOL_ASK);

      double sl = cmd.stop_loss;
      double tp = cmd.take_profit;

      if(UseATRBasedSLTP && (sl <= 0 || tp <= 0))
         ComputeATRSltp(cmd.symbol, true, req.price, sl, tp);

      if(sl > 0) req.sl = NormalizeDouble(sl, digits);
      if(tp > 0) req.tp = NormalizeDouble(tp, digits);
   }
   else // sell
   {
      req.type  = ORDER_TYPE_SELL;
      req.price = SymbolInfoDouble(cmd.symbol, SYMBOL_BID);

      double sl = cmd.stop_loss;
      double tp = cmd.take_profit;

      if(UseATRBasedSLTP && (sl <= 0 || tp <= 0))
         ComputeATRSltp(cmd.symbol, false, req.price, sl, tp);

      if(sl > 0) req.sl = NormalizeDouble(sl, digits);
      if(tp > 0) req.tp = NormalizeDouble(tp, digits);
   }

   if(DetailedLogging)
      Print("Executing trade: ", cmd.action, " ", req.volume, " ", cmd.symbol,
            " @ ", req.price, " SL:", req.sl, " TP:", req.tp);

   bool sent = OrderSend(req, res);
   if(DetailedLogging)
      Print("Order result - Sent: ", sent, " RetCode: ", res.retcode,
            " Deal: ", res.deal, " Order: ", res.order);

   return (sent && res.retcode == TRADE_RETCODE_DONE);
}

bool ExecuteModifyCommand(TradeCommand &cmd)
{
   if(!PositionSelectByTicket(cmd.ticket))
   {
      Print("Error: Position ticket ", cmd.ticket, " not found");
      return false;
   }
   
   string symbol = PositionGetString(POSITION_SYMBOL);
   MqlTradeRequest req; MqlTradeResult  res;
   ZeroMemory(req); ZeroMemory(res);

   req.action = TRADE_ACTION_SLTP;
   req.position = cmd.ticket;
   req.symbol = symbol;

   double current_sl = PositionGetDouble(POSITION_SL);
   double current_tp = PositionGetDouble(POSITION_TP);
   req.sl = (cmd.stop_loss  > 0) ? NormalizeDouble(cmd.stop_loss, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)) : current_sl;
   req.tp = (cmd.take_profit> 0) ? NormalizeDouble(cmd.take_profit,(int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)) : current_tp;

   if(DetailedLogging) Print("Modifying position ", cmd.ticket, " - New SL: ", req.sl, " New TP: ", req.tp);

   bool sent = OrderSend(req, res);
   if(DetailedLogging) Print("Modify result - Sent: ", sent, " RetCode: ", res.retcode);
   return(sent && res.retcode == TRADE_RETCODE_DONE);
}

bool ExecuteCloseCommand(TradeCommand &cmd)
{
   if(!PositionSelectByTicket(cmd.ticket))
   {
      Print("Error: Position ticket ", cmd.ticket, " not found");
      return false;
   }
   
   string symbol = PositionGetString(POSITION_SYMBOL);
   double pos_volume = PositionGetDouble(POSITION_VOLUME);
   long type = PositionGetInteger(POSITION_TYPE);
   
   MqlTradeRequest req; MqlTradeResult  res;
   ZeroMemory(req); ZeroMemory(res);

   req.action = TRADE_ACTION_DEAL;
   req.position = cmd.ticket;
   req.symbol = symbol;
   // Determine desired close volume (partial or full)
   double desired_volume = pos_volume;
   if(cmd.close_volume > 0 && cmd.close_volume < pos_volume)
      desired_volume = cmd.close_volume;
   
   // Normalize to broker volume step/min/max
   double vmin = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double vstep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(vmin <= 0) vmin = 0.01;
   if(vmax <= 0) vmax = pos_volume;
   if(vstep <= 0) vstep = 0.01;
   
   desired_volume = MathMax(vmin, MathMin(desired_volume, vmax));
   desired_volume = MathFloor(desired_volume / vstep) * vstep;
   if(desired_volume <= 0)
   {
      Print("Error: desired close volume invalid: ", desired_volume);
      return false;
   }
   req.volume = NormalizeDouble(desired_volume, 2);
   req.deviation = 50;
   req.type_filling = ORDER_FILLING_IOC;

   if(type == POSITION_TYPE_BUY)
   {
      req.type = ORDER_TYPE_SELL;
      req.price = SymbolInfoDouble(symbol, SYMBOL_BID);
   }
   else
   {
      req.type = ORDER_TYPE_BUY;
      req.price = SymbolInfoDouble(symbol, SYMBOL_ASK);
   }

   req.comment = (cmd.comment != "") ? cmd.comment : "Manual close";

   if(DetailedLogging) Print("Closing position ", cmd.ticket, " - Volume: ", req.volume, " @ ", req.price);

   bool sent = OrderSend(req, res);
   if(DetailedLogging) Print("Close result - Sent: ", sent, " RetCode: ", res.retcode, " Deal: ", res.deal);
   return(sent && res.retcode == TRADE_RETCODE_DONE);
}

// --------------------------- Logging & commands -------------------
void LogTradeAction(string action, bool result, TradeCommand &cmd)
{
   int handle = FileOpen("trade_results.txt", FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_READ);
   if(handle != INVALID_HANDLE)
   {
      FileSeek(handle, 0, SEEK_END);
      string msg = TimeToString(TimeCurrent()) + " | " + action + " | " + (result ? "SUCCESS" : "FAIL") + " | ";
      if(action == "modify" || action == "close") msg += "ticket:" + IntegerToString(cmd.ticket) + " | ";
      else msg += DoubleToString(cmd.lot_size, 2) + " | ";
      msg += cmd.symbol + " | " + cmd.trade_id;
      FileWrite(handle, msg);
      FileClose(handle);
   }
   if(DetailedLogging)
      Print("Trade logged: ", action, " ", (result ? "SUCCESS" : "FAIL"), " Symbol: ", cmd.symbol, " TradeID: ", cmd.trade_id);
}

void CheckTradeCommands()
{
   int handle = FileOpen("commands.json", FILE_READ|FILE_TXT|FILE_ANSI);
   if(handle == INVALID_HANDLE) return;

   string cmd = "";
   string line;
   while(!FileIsEnding(handle))
   {
      line = FileReadString(handle);
      cmd += line;
   }
   FileClose(handle);

   if(StringLen(cmd) < 10) return;
   if(DetailedLogging) Print("Received command: ", cmd);

   TradeCommand trade_cmd;
   if(ParseTradeCommand(cmd, trade_cmd))
   {
      bool result = false;
      if(trade_cmd.action=="buy" || trade_cmd.action=="sell") result = ExecuteBuySellCommand(trade_cmd);
      else if(trade_cmd.action=="modify") result = ExecuteModifyCommand(trade_cmd);
      else if(trade_cmd.action=="close")  result = ExecuteCloseCommand(trade_cmd);

      LogTradeAction(trade_cmd.action, result, trade_cmd);

      int h = FileOpen("commands.json", FILE_WRITE|FILE_TXT|FILE_ANSI);
      if(h != INVALID_HANDLE) { FileWrite(h, "{}"); FileClose(h); }
   }
   else
   {
      if(DetailedLogging) Print("Failed to parse command: ", cmd);
   }
}
