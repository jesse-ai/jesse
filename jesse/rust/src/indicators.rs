use pyo3::prelude::*;
use numpy::{PyArray1, PyReadonlyArray1, PyReadonlyArray2};
use ndarray::{Array1, s};

/// Calculate RSI (Relative Strength Index)
#[pyfunction]
pub fn rsi(source: PyReadonlyArray1<f64>, period: usize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        let source_array = source.as_array();
        let n = source_array.len();
        let mut result = Array1::<f64>::from_elem(n, f64::NAN);

        if n <= period {
            return Ok(PyArray1::from_array(py, &result).to_owned());
        }

        // Calculate initial sum of gains and losses
        let mut sum_gain = 0.0;
        let mut sum_loss = 0.0;
        for i in 1..=period {
            let change = source_array[i] - source_array[i - 1];
            if change > 0.0 {
                sum_gain += change;
            } else {
                sum_loss += change.abs();
            }
        }

        let mut avg_gain = sum_gain / period as f64;
        let mut avg_loss = sum_loss / period as f64;

        // Calculate first RSI value
        if avg_loss == 0.0 {
            result[period] = 100.0;
        } else {
            let rs = avg_gain / avg_loss;
            result[period] = 100.0 - (100.0 / (1.0 + rs));
        }

        // Calculate subsequent RSI values using Wilder's smoothing
        for i in (period + 1)..n {
            let change = source_array[i] - source_array[i - 1];
            let (current_gain, current_loss) = if change > 0.0 {
                (change, 0.0)
            } else {
                (0.0, change.abs())
            };

            avg_gain = (avg_gain * (period as f64 - 1.0) + current_gain) / period as f64;
            avg_loss = (avg_loss * (period as f64 - 1.0) + current_loss) / period as f64;

            if avg_loss == 0.0 {
                result[i] = 100.0;
            } else {
                let rs = avg_gain / avg_loss;
                result[i] = 100.0 - (100.0 / (1.0 + rs));
            }
        }

        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}

/// Calculate KAMA (Kaufman Adaptive Moving Average) - Optimized version
#[pyfunction]
pub fn kama(source: PyReadonlyArray1<f64>, period: usize, fast_length: usize, slow_length: usize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        let source_array = source.as_array();
        let n = source_array.len();
        
        let mut result = Array1::<f64>::zeros(n);
        
        if n <= period {
            // Fill with source values when we don't have enough data
            for i in 0..n {
                result[i] = source_array[i];
            }
            return Ok(PyArray1::from_array(py, &result).to_owned());
        }
        
        // Calculate the efficiency ratio multiplier
        let fast_alpha = 2.0 / (fast_length as f64 + 1.0);
        let slow_alpha = 2.0 / (slow_length as f64 + 1.0);
        let alpha_diff = fast_alpha - slow_alpha;
        
        // First 'period' values are same as source
        for i in 0..period {
            result[i] = source_array[i];
        }
        
        // Pre-calculate price differences for rolling volatility
        let mut price_diffs = Vec::with_capacity(n - 1);
        for i in 1..n {
            price_diffs.push((source_array[i] - source_array[i - 1]).abs());
        }
        
        // Initialize rolling volatility sum for the first window
        let mut volatility_sum = 0.0;
        for i in 0..(period - 1) {
            volatility_sum += price_diffs[i];
        }
        
        // Start the calculation after the initial period
        for i in period..n {
            // Calculate Efficiency Ratio using rolling volatility
            let change = (source_array[i] - source_array[i - period]).abs();
            
            // Update rolling volatility sum
            if i >= period {
                // Add new difference, remove old difference
                volatility_sum += price_diffs[i - 1]; // Current period's difference
                if i > period {
                    volatility_sum -= price_diffs[i - period - 1]; // Remove oldest difference
                }
            }
            
            let er = if volatility_sum != 0.0 { change / volatility_sum } else { 0.0 };
            
            // Calculate smoothing constant
            let sc = (er * alpha_diff + slow_alpha).powi(2);
            
            // Calculate KAMA
            result[i] = result[i - 1] + sc * (source_array[i] - result[i - 1]);
        }
        
        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}

/// Calculate Ichimoku Cloud
#[pyfunction]
pub fn ichimoku_cloud(
    candles: PyReadonlyArray2<f64>,
    conversion_line_period: usize,
    base_line_period: usize,
    lagging_line_period: usize,
    displacement: usize
) -> PyResult<(f64, f64, f64, f64)> {
    Python::with_gil(|_py| {
        let candles_array = candles.as_array();
        
        // Get the high and low price columns
        let high_prices = candles_array.slice(s![.., 3]);
        let low_prices = candles_array.slice(s![.., 4]);
        
        // Calculate for earlier period (displaced)
        let earlier_high = high_prices.slice(s![..-((displacement as isize) - 1)]);
        let earlier_low = low_prices.slice(s![..-((displacement as isize) - 1)]);
        
        // Helper function to get period high and low
        let get_period_hl = |highs: ndarray::ArrayView1<f64>, lows: ndarray::ArrayView1<f64>, period: usize| -> (f64, f64) {
            let n = highs.len();
            if n < period {
                return (f64::NAN, f64::NAN);
            }
            
            // Instead of negative slicing, use the last 'period' elements
            let start_idx = n.saturating_sub(period);
            let period_high = highs.slice(s![start_idx..]).fold(f64::NEG_INFINITY, |a, &b| a.max(b));
            let period_low = lows.slice(s![start_idx..]).fold(f64::INFINITY, |a, &b| a.min(b));
            
            (period_high, period_low)
        };
        
        // Earlier periods calculations
        let (small_ph, small_pl) = get_period_hl(earlier_high, earlier_low, conversion_line_period);
        let (mid_ph, mid_pl) = get_period_hl(earlier_high, earlier_low, base_line_period);
        let (long_ph, long_pl) = get_period_hl(earlier_high, earlier_low, lagging_line_period);
        
        let early_conversion_line = (small_ph + small_pl) / 2.0;
        let early_base_line = (mid_ph + mid_pl) / 2.0;
        let span_a = (early_conversion_line + early_base_line) / 2.0;
        let span_b = (long_ph + long_pl) / 2.0;
        
        // Current period calculations
        let (current_small_ph, current_small_pl) = get_period_hl(high_prices, low_prices, conversion_line_period);
        let (current_mid_ph, current_mid_pl) = get_period_hl(high_prices, low_prices, base_line_period);
        
        let current_conversion_line = (current_small_ph + current_small_pl) / 2.0;
        let current_base_line = (current_mid_ph + current_mid_pl) / 2.0;
        
        Ok((current_conversion_line, current_base_line, span_a, span_b))
    })
}

/// Calculate SRSI (Stochastic RSI) - Optimized version
#[pyfunction]
pub fn srsi(source: PyReadonlyArray1<f64>, period: usize, period_stoch: usize, k_period: usize, d_period: usize) -> PyResult<(Py<PyArray1<f64>>, Py<PyArray1<f64>>)> {
    Python::with_gil(|py| {
        let source_array = source.as_array();
        let n = source_array.len();
        
        let mut k_values = Array1::<f64>::from_elem(n, f64::NAN);
        let mut d_values = Array1::<f64>::from_elem(n, f64::NAN);
        
        if n <= period {
            return Ok((
                PyArray1::from_array(py, &k_values).to_owned(),
                PyArray1::from_array(py, &d_values).to_owned()
            ));
        }

        // Inline RSI calculation with rolling stochastic
        let mut sum_gain = 0.0;
        let mut sum_loss = 0.0;
        
        // Calculate initial RSI values
        for i in 1..=period {
            let change = source_array[i] - source_array[i - 1];
            if change > 0.0 {
                sum_gain += change;
            } else {
                sum_loss += change.abs();
            }
        }
        
        let mut avg_gain = sum_gain / period as f64;
        let mut avg_loss = sum_loss / period as f64;
        
        // Rolling buffers for stochastic calculation
        let mut rsi_buffer = std::collections::VecDeque::with_capacity(period_stoch);
        let mut k_buffer = std::collections::VecDeque::with_capacity(k_period);
        
        // Process each data point
        for i in period..n {
            // Calculate RSI for current point
            let rsi_val = if i == period {
                // First RSI value
                if avg_loss == 0.0 {
                    100.0
                } else {
                    let rs = avg_gain / avg_loss;
                    100.0 - (100.0 / (1.0 + rs))
                }
            } else {
                // Subsequent RSI values using Wilder's smoothing
                let change = source_array[i] - source_array[i - 1];
                let (current_gain, current_loss) = if change > 0.0 {
                    (change, 0.0)
                } else {
                    (0.0, change.abs())
                };
                
                avg_gain = (avg_gain * (period as f64 - 1.0) + current_gain) / period as f64;
                avg_loss = (avg_loss * (period as f64 - 1.0) + current_loss) / period as f64;
                
                if avg_loss == 0.0 {
                    100.0
                } else {
                    let rs = avg_gain / avg_loss;
                    100.0 - (100.0 / (1.0 + rs))
                }
            };
            
            // Add to RSI buffer
            rsi_buffer.push_back(rsi_val);
            if rsi_buffer.len() > period_stoch {
                rsi_buffer.pop_front();
            }
            
            // Calculate %K when we have enough RSI values
            if rsi_buffer.len() == period_stoch {
                let rsi_min = rsi_buffer.iter().fold(f64::INFINITY, |a, &b| a.min(b));
                let rsi_max = rsi_buffer.iter().fold(f64::NEG_INFINITY, |a, &b| a.max(b));
                
                let k_val = if rsi_max != rsi_min {
                    100.0 * (rsi_val - rsi_min) / (rsi_max - rsi_min)
                } else {
                    f64::NAN
                };
                
                if k_period > 1 {
                    // Smooth %K
                    k_buffer.push_back(k_val);
                    if k_buffer.len() > k_period {
                        k_buffer.pop_front();
                    }
                    
                    if k_buffer.len() == k_period && k_buffer.iter().all(|&x| !x.is_nan()) {
                        let k_smoothed = k_buffer.iter().sum::<f64>() / k_period as f64;
                        k_values[i] = k_smoothed;
                    }
                } else {
                    // No smoothing needed
                    k_values[i] = k_val;
                }
            }
        }
        
        // Calculate %D (SMA of %K) using rolling sum
        if d_period > 0 {
            let mut d_buffer = std::collections::VecDeque::with_capacity(d_period);
            
            for i in 0..n {
                if !k_values[i].is_nan() {
                    d_buffer.push_back(k_values[i]);
                    if d_buffer.len() > d_period {
                        d_buffer.pop_front();
                    }
                    
                    if d_buffer.len() == d_period {
                        d_values[i] = d_buffer.iter().sum::<f64>() / d_period as f64;
                    }
                }
            }
        }
        
        Ok((
            PyArray1::from_array(py, &k_values).to_owned(),
            PyArray1::from_array(py, &d_values).to_owned()
        ))
    })
}

/// Calculate ADX (Average Directional Index)
#[pyfunction]
pub fn adx(candles: PyReadonlyArray2<f64>, period: usize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        let candles_array = candles.as_array();
        let n = candles_array.shape()[0];
        let mut adx_result = Array1::<f64>::from_elem(n, f64::NAN);

        let required_len = 2 * period;
        if n <= required_len {
            return Ok(PyArray1::from_array(py, &adx_result).to_owned());
        }

        let high = candles_array.slice(s![.., 3]);
        let low = candles_array.slice(s![.., 4]);
        let close = candles_array.slice(s![.., 2]);

        // State for Wilder smoothing
        let mut tr_smooth: f64 = 0.0;
        let mut plus_dm_smooth: f64 = 0.0;
        let mut minus_dm_smooth: f64 = 0.0;
        
        // Buffer for DX values to calculate the first ADX
        let mut dx_buffer: Vec<f64> = Vec::with_capacity(period);

        // Main calculation loop
        for i in 1..n {
            // 1. Calculate raw TR, +DM, -DM for current step `i`
            let hl = high[i] - low[i];
            let hc = (high[i] - close[i - 1]).abs();
            let lc = (low[i] - close[i - 1]).abs();
            let current_tr = hl.max(hc).max(lc);

            let h_diff = high[i] - high[i - 1];
            let l_diff = low[i - 1] - low[i];

            let mut current_plus_dm = 0.0;
            if h_diff > l_diff && h_diff > 0.0 {
                current_plus_dm = h_diff;
            }

            let mut current_minus_dm = 0.0;
            if l_diff > h_diff && l_diff > 0.0 {
                current_minus_dm = l_diff;
            }

            // 2. Update smoothed values
            if i <= period {
                // Accumulate for the first smoothed value
                tr_smooth += current_tr;
                plus_dm_smooth += current_plus_dm;
                minus_dm_smooth += current_minus_dm;
            } else {
                // Apply Wilder's smoothing formula
                tr_smooth = tr_smooth - (tr_smooth / period as f64) + current_tr;
                plus_dm_smooth = plus_dm_smooth - (plus_dm_smooth / period as f64) + current_plus_dm;
                minus_dm_smooth = minus_dm_smooth - (minus_dm_smooth / period as f64) + current_minus_dm;
            }
            
            // From index `period` onwards, we can calculate DI and DX
            if i >= period {
                let mut current_dx = 0.0;
                if tr_smooth != 0.0 {
                    let di_plus = 100.0 * plus_dm_smooth / tr_smooth;
                    let di_minus = 100.0 * minus_dm_smooth / tr_smooth;
                    let di_sum = di_plus + di_minus;
                    if di_sum != 0.0 {
                        current_dx = 100.0 * (di_plus - di_minus).abs() / di_sum;
                    }
                }
                
                // Store DX value for initial ADX calculation, or calculate ADX
                if i < required_len {
                    dx_buffer.push(current_dx);
                } else {
                    if i == required_len {
                        // First ADX value is the average of the buffer
                        let dx_sum: f64 = dx_buffer.iter().sum();
                        adx_result[i] = dx_sum / period as f64;
                    } else {
                        // Subsequent ADX values are smoothed
                        if !adx_result[i - 1].is_nan() {
                           adx_result[i] = (adx_result[i - 1] * (period - 1) as f64 + current_dx) / period as f64;
                        }
                    }
                }
            }
        }

        Ok(PyArray1::from_array(py, &adx_result).to_owned())
    })
}

/// Calculate TEMA (Triple Exponential Moving Average)
#[pyfunction]
pub fn tema(source: PyReadonlyArray1<f64>, period: usize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        let source_array = source.as_array();
        let n = source_array.len();
        let mut result = Array1::<f64>::zeros(n);

        if n == 0 {
            return Ok(PyArray1::from_array(py, &result).to_owned());
        }

        let alpha = 2.0 / (period as f64 + 1.0);
        let mut ema1 = source_array[0];
        let mut ema2 = ema1;
        let mut ema3 = ema2;

        result[0] = 3.0 * ema1 - 3.0 * ema2 + ema3;

        for i in 1..n {
            ema1 = alpha * source_array[i] + (1.0 - alpha) * ema1;
            ema2 = alpha * ema1 + (1.0 - alpha) * ema2;
            ema3 = alpha * ema2 + (1.0 - alpha) * ema3;
            result[i] = 3.0 * ema1 - 3.0 * ema2 + ema3;
        }

        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}

/// Calculate MACD (Moving Average Convergence/Divergence)
#[pyfunction]
pub fn macd(source: PyReadonlyArray1<f64>, fast_period: usize, slow_period: usize, signal_period: usize) -> PyResult<(Py<PyArray1<f64>>, Py<PyArray1<f64>>, Py<PyArray1<f64>>)> {
    Python::with_gil(|py| {
        let source_array = source.as_array();
        let n = source_array.len();
        
        let mut macd_line_result = Array1::<f64>::zeros(n);
        let mut signal_line_result = Array1::<f64>::zeros(n);
        let mut hist_result = Array1::<f64>::zeros(n);

        if n == 0 {
            return Ok((
                PyArray1::from_array(py, &macd_line_result).to_owned(),
                PyArray1::from_array(py, &signal_line_result).to_owned(),
                PyArray1::from_array(py, &hist_result).to_owned(),
            ));
        }

        let alpha_fast = 2.0 / (fast_period as f64 + 1.0);
        let alpha_slow = 2.0 / (slow_period as f64 + 1.0);
        let alpha_signal = 2.0 / (signal_period as f64 + 1.0);

        let mut ema_fast = source_array[0];
        let mut ema_slow = source_array[0];
        
        let macd_val = ema_fast - ema_slow;
        let macd_val_cleaned = if macd_val.is_nan() { 0.0 } else { macd_val };
        
        let mut signal_ema = macd_val_cleaned;

        macd_line_result[0] = macd_val_cleaned;
        signal_line_result[0] = signal_ema;
        hist_result[0] = macd_val - signal_ema;

        for i in 1..n {
            ema_fast = alpha_fast * source_array[i] + (1.0 - alpha_fast) * ema_fast;
            ema_slow = alpha_slow * source_array[i] + (1.0 - alpha_slow) * ema_slow;

            let macd_val = ema_fast - ema_slow;
            let macd_val_cleaned = if macd_val.is_nan() { 0.0 } else { macd_val };
            
            signal_ema = alpha_signal * macd_val_cleaned + (1.0 - alpha_signal) * signal_ema;
            
            let hist_val = macd_val - signal_ema;

            macd_line_result[i] = macd_val_cleaned;
            signal_line_result[i] = signal_ema;
            hist_result[i] = hist_val;
        }

        Ok((
            PyArray1::from_array(py, &macd_line_result).to_owned(),
            PyArray1::from_array(py, &signal_line_result).to_owned(),
            PyArray1::from_array(py, &hist_result).to_owned(),
        ))
    })
}

/// Calculate Bollinger Bands Width - Optimized version
#[pyfunction]
pub fn bollinger_bands_width(source: PyReadonlyArray1<f64>, period: usize, mult: f64) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        let source_array = source.as_array();
        let n = source_array.len();
        let mut result = Array1::<f64>::from_elem(n, f64::NAN);

        if n < period {
            return Ok(PyArray1::from_array(py, &result).to_owned());
        }

        // Use rolling window for efficient calculation
        let mut sum = 0.0;
        let mut sum_sq = 0.0;
        
        // Initialize first window
        for i in 0..period {
            let val = source_array[i];
            sum += val;
            sum_sq += val * val;
        }
        
        // Calculate first BBW value
        let sma = sum / period as f64;
        let variance = (sum_sq / period as f64) - (sma * sma);
        let std_dev = variance.sqrt();
        
        // Calculate Bollinger Bands Width
        if sma != 0.0 {
            let upper_band = sma + mult * std_dev;
            let lower_band = sma - mult * std_dev;
            result[period - 1] = (upper_band - lower_band) / sma;
        }
        
        // Calculate subsequent values using rolling window
        for i in period..n {
            let old_val = source_array[i - period];
            let new_val = source_array[i];
            
            // Update rolling sums
            sum = sum - old_val + new_val;
            sum_sq = sum_sq - (old_val * old_val) + (new_val * new_val);
            
            // Calculate SMA and standard deviation
            let sma = sum / period as f64;
            let variance = (sum_sq / period as f64) - (sma * sma);
            let std_dev = variance.sqrt();
            
            // Calculate Bollinger Bands Width
            if sma != 0.0 {
                let upper_band = sma + mult * std_dev;
                let lower_band = sma - mult * std_dev;
                result[i] = (upper_band - lower_band) / sma;
            }
        }

        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}

/// Calculate Bollinger Bands - Optimized version
#[pyfunction]
pub fn bollinger_bands(source: PyReadonlyArray1<f64>, period: usize, devup: f64, devdn: f64) -> PyResult<(Py<PyArray1<f64>>, Py<PyArray1<f64>>, Py<PyArray1<f64>>)> {
    Python::with_gil(|py| {
        let source_array = source.as_array();
        let n = source_array.len();
        
        let mut upper_band = Array1::<f64>::from_elem(n, f64::NAN);
        let mut middle_band = Array1::<f64>::from_elem(n, f64::NAN);
        let mut lower_band = Array1::<f64>::from_elem(n, f64::NAN);

        if n < period {
            return Ok((
                PyArray1::from_array(py, &upper_band).to_owned(),
                PyArray1::from_array(py, &middle_band).to_owned(),
                PyArray1::from_array(py, &lower_band).to_owned()
            ));
        }

        // Use rolling window for efficient calculation
        let mut sum = 0.0;
        let mut sum_sq = 0.0;
        
        // Initialize first window
        for i in 0..period {
            let val = source_array[i];
            sum += val;
            sum_sq += val * val;
        }
        
        // Calculate first Bollinger Bands values
        let sma = sum / period as f64;
        let variance = (sum_sq / period as f64) - (sma * sma);
        let std_dev = variance.sqrt();
        
        middle_band[period - 1] = sma;
        upper_band[period - 1] = sma + devup * std_dev;
        lower_band[period - 1] = sma - devdn * std_dev;
        
        // Calculate subsequent values using rolling window
        for i in period..n {
            let old_val = source_array[i - period];
            let new_val = source_array[i];
            
            // Update rolling sums
            sum = sum - old_val + new_val;
            sum_sq = sum_sq - (old_val * old_val) + (new_val * new_val);
            
            // Calculate SMA and standard deviation
            let sma = sum / period as f64;
            let variance = (sum_sq / period as f64) - (sma * sma);
            let std_dev = variance.sqrt();
            
            // Calculate bands
            middle_band[i] = sma;
            upper_band[i] = sma + devup * std_dev;
            lower_band[i] = sma - devdn * std_dev;
        }

        Ok((
            PyArray1::from_array(py, &upper_band).to_owned(),
            PyArray1::from_array(py, &middle_band).to_owned(),
            PyArray1::from_array(py, &lower_band).to_owned()
        ))
    })
}

/// Shift array by a given number of periods
#[pyfunction]
pub fn shift(source: PyReadonlyArray1<f64>, periods: isize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        let source_array = source.as_array();
        let n = source_array.len();
        let mut result = Array1::<f64>::from_elem(n, f64::NAN);

        if periods == 0 {
            // No shift, return copy of source
            for i in 0..n {
                result[i] = source_array[i];
            }
        } else if periods > 0 {
            // Shift right (positive periods)
            let shift_amount = periods as usize;
            if shift_amount < n {
                for i in shift_amount..n {
                    result[i] = source_array[i - shift_amount];
                }
            }
        } else {
            // Shift left (negative periods)
            let shift_amount = (-periods) as usize;
            if shift_amount < n {
                for i in 0..(n - shift_amount) {
                    result[i] = source_array[i + shift_amount];
                }
            }
        }

        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}

/// Calculate moving standard deviation
#[pyfunction]
pub fn moving_std(source: PyReadonlyArray1<f64>, period: usize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        let source_array = source.as_array();
        let n = source_array.len();
        let mut result = Array1::<f64>::from_elem(n, f64::NAN);

        if n < period {
            return Ok(PyArray1::from_array(py, &result).to_owned());
        }

        // Calculate moving standard deviation
        for i in (period - 1)..n {
            let start_idx = i + 1 - period;
            let window = source_array.slice(s![start_idx..=i]);
            
            // Calculate mean
            let mean = window.sum() / period as f64;
            
            // Calculate variance
            let variance = window.iter()
                .map(|&x| (x - mean).powi(2))
                .sum::<f64>() / period as f64;
            
            // Calculate standard deviation
            result[i] = variance.sqrt();
        }

        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}

/// Calculate Simple Moving Average (SMA)
#[pyfunction]
pub fn sma(source: PyReadonlyArray1<f64>, period: usize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        let source_array = source.as_array();
        let n = source_array.len();
        let mut result = Array1::<f64>::from_elem(n, f64::NAN);

        if n < period {
            return Ok(PyArray1::from_array(py, &result).to_owned());
        }

        // Calculate first SMA value
        let mut sum = 0.0;
        let mut count = 0;
        for i in 0..period {
            if !source_array[i].is_nan() {
                sum += source_array[i];
                count += 1;
            }
        }
        if count > 0 {
            result[period - 1] = sum / count as f64;
        }

        // Calculate subsequent SMA values using sliding window
        for i in period..n {
            if !source_array[i - period].is_nan() {
                sum -= source_array[i - period];
                count -= 1;
            }
            if !source_array[i].is_nan() {
                sum += source_array[i];
                count += 1;
            }
            if count > 0 {
                result[i] = sum / count as f64;
            }
        }

        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}

/// Calculate SMMA (Smoothed Moving Average)
#[pyfunction]
pub fn smma(source: PyReadonlyArray1<f64>, length: usize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        // Convert PyArray to rust ndarray
        let source_array = source.as_array();
        let n = source_array.len();
        
        // Create output array
        let mut result = Array1::<f64>::zeros(n);
        
        if n < length {
            // Return array of NaNs if we don't have enough data
            for i in 0..n {
                result[i] = f64::NAN;
            }
            return Ok(PyArray1::from_array(py, &result).to_owned());
        }
        
        // Calculate first SMMA value (SMA)
        let alpha = 1.0 / (length as f64);
        let mut total = 0.0;
        for i in 0..length {
            total += source_array[i];
        }
        let init_val = total / (length as f64);
        
        // Set first value
        result[length - 1] = init_val;
        
        // Calculate subsequent SMMA values
        for i in length..n {
            result[i] = alpha * source_array[i] + (1.0 - alpha) * result[i - 1];
        }
        
        // Fill initial values with NaN
        for i in 0..(length - 1) {
            result[i] = f64::NAN;
        }
        
        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}

/// Calculate Alligator indicator (Jaw, Teeth, Lips) - Optimized version
#[pyfunction]
pub fn alligator(source: PyReadonlyArray1<f64>) -> PyResult<(Py<PyArray1<f64>>, Py<PyArray1<f64>>, Py<PyArray1<f64>>)> {
    Python::with_gil(|py| {
        let source_array = source.as_array();
        let n = source_array.len();
        
        // Initialize result arrays
        let mut jaw = Array1::<f64>::from_elem(n, f64::NAN);
        let mut teeth = Array1::<f64>::from_elem(n, f64::NAN);
        let mut lips = Array1::<f64>::from_elem(n, f64::NAN);
        
        if n < 13 {  // Need at least 13 periods for jaw (longest period)
            return Ok((
                PyArray1::from_array(py, &jaw).to_owned(),
                PyArray1::from_array(py, &teeth).to_owned(),
                PyArray1::from_array(py, &lips).to_owned()
            ));
        }
        
        // SMMA parameters
        let jaw_period = 13;
        let teeth_period = 8;
        let lips_period = 5;
        
        let jaw_alpha = 1.0 / jaw_period as f64;
        let teeth_alpha = 1.0 / teeth_period as f64;
        let lips_alpha = 1.0 / lips_period as f64;
        
        // Calculate initial SMA values for each line
        let mut jaw_sum = 0.0;
        let mut teeth_sum = 0.0;
        let mut lips_sum = 0.0;
        
        // Accumulate sums for initial values
        for i in 0..jaw_period {
            jaw_sum += source_array[i];
            if i < teeth_period {
                teeth_sum += source_array[i];
            }
            if i < lips_period {
                lips_sum += source_array[i];
            }
        }
        
        // Initialize SMMA values (without shifts)
        let mut jaw_smma = jaw_sum / jaw_period as f64;
        let mut teeth_smma = teeth_sum / teeth_period as f64;
        let mut lips_smma = lips_sum / lips_period as f64;
        
        // Calculate all SMMA values first, then apply shifts
        let mut jaw_unshifted = Array1::<f64>::from_elem(n, f64::NAN);
        let mut teeth_unshifted = Array1::<f64>::from_elem(n, f64::NAN);
        let mut lips_unshifted = Array1::<f64>::from_elem(n, f64::NAN);
        
        // Set initial SMMA values
        jaw_unshifted[jaw_period - 1] = jaw_smma;
        teeth_unshifted[teeth_period - 1] = teeth_smma;
        lips_unshifted[lips_period - 1] = lips_smma;
        
        // Calculate subsequent SMMA values using single pass
        for i in jaw_period..n {
            // Update jaw (13-period SMMA)
            jaw_smma = jaw_alpha * source_array[i] + (1.0 - jaw_alpha) * jaw_smma;
            jaw_unshifted[i] = jaw_smma;
            
            // Update teeth (8-period SMMA) if we have enough data
            if i >= teeth_period {
                teeth_smma = teeth_alpha * source_array[i] + (1.0 - teeth_alpha) * teeth_smma;
                teeth_unshifted[i] = teeth_smma;
            }
            
            // Update lips (5-period SMMA) if we have enough data
            if i >= lips_period {
                lips_smma = lips_alpha * source_array[i] + (1.0 - lips_alpha) * lips_smma;
                lips_unshifted[i] = lips_smma;
            }
        }
        
        // Apply shifts inline (forward shifts)
        // Jaw: shift by 8 periods forward
        for i in 0..(n - 8) {
            if i + 8 < n && !jaw_unshifted[i].is_nan() {
                jaw[i + 8] = jaw_unshifted[i];
            }
        }
        
        // Teeth: shift by 5 periods forward
        for i in 0..(n - 5) {
            if i + 5 < n && !teeth_unshifted[i].is_nan() {
                teeth[i + 5] = teeth_unshifted[i];
            }
        }
        
        // Lips: shift by 3 periods forward
        for i in 0..(n - 3) {
            if i + 3 < n && !lips_unshifted[i].is_nan() {
                lips[i + 3] = lips_unshifted[i];
            }
        }
        
        Ok((
            PyArray1::from_array(py, &jaw).to_owned(),
            PyArray1::from_array(py, &teeth).to_owned(),
            PyArray1::from_array(py, &lips).to_owned()
        ))
    })
} 

/// Calculate DI (Directional Indicator) - Optimized version
#[pyfunction]
pub fn di(candles: PyReadonlyArray2<f64>, period: usize) -> PyResult<(Py<PyArray1<f64>>, Py<PyArray1<f64>>)> {
    Python::with_gil(|py| {
        let candles_array = candles.as_array();
        let n = candles_array.nrows();
        
        // Initialize result arrays
        let mut plus_di = Array1::<f64>::from_elem(n, f64::NAN);
        let mut minus_di = Array1::<f64>::from_elem(n, f64::NAN);
        
        if n < 2 || n < period + 1 {
            return Ok((
                PyArray1::from_array(py, &plus_di).to_owned(),
                PyArray1::from_array(py, &minus_di).to_owned()
            ));
        }
        
        // Extract OHLCV data (assuming standard format: open, high, low, close, volume)
        let high = candles_array.column(3);
        let low = candles_array.column(4);
        let close = candles_array.column(2);
        
        // Initialize smoothed values for Wilder's smoothing
        let mut tr_smooth = 0.0;
        let mut plus_dm_smooth = 0.0;
        let mut minus_dm_smooth = 0.0;
        
        // Calculate initial sums for the first 'period' values
        for i in 1..=period {
            // Calculate True Range (TR)
            let hl = high[i] - low[i];
            let hc = (high[i] - close[i - 1]).abs();
            let lc = (low[i] - close[i - 1]).abs();
            let current_tr = hl.max(hc).max(lc);
            
            // Calculate Directional Movements (+DM and -DM)
            let h_diff = high[i] - high[i - 1];
            let l_diff = low[i - 1] - low[i];
            
            let current_plus_dm = if h_diff > l_diff && h_diff > 0.0 { h_diff } else { 0.0 };
            let current_minus_dm = if l_diff > h_diff && l_diff > 0.0 { l_diff } else { 0.0 };
            
            // Accumulate for initial smoothed values
            tr_smooth += current_tr;
            plus_dm_smooth += current_plus_dm;
            minus_dm_smooth += current_minus_dm;
        }
        
        // Calculate first DI values at index 'period'
        if tr_smooth > 0.0 {
            plus_di[period] = 100.0 * plus_dm_smooth / tr_smooth;
            minus_di[period] = 100.0 * minus_dm_smooth / tr_smooth;
        } else {
            plus_di[period] = 0.0;
            minus_di[period] = 0.0;
        }
        
        // Calculate subsequent DI values using Wilder's smoothing
        for i in (period + 1)..n {
            // Calculate current TR, +DM, -DM
            let hl = high[i] - low[i];
            let hc = (high[i] - close[i - 1]).abs();
            let lc = (low[i] - close[i - 1]).abs();
            let current_tr = hl.max(hc).max(lc);
            
            let h_diff = high[i] - high[i - 1];
            let l_diff = low[i - 1] - low[i];
            
            let current_plus_dm = if h_diff > l_diff && h_diff > 0.0 { h_diff } else { 0.0 };
            let current_minus_dm = if l_diff > h_diff && l_diff > 0.0 { l_diff } else { 0.0 };
            
            // Apply Wilder's smoothing: smoothed[i] = (smoothed[i-1] * (period - 1) + current) / period
            tr_smooth = (tr_smooth * (period - 1) as f64 + current_tr) / period as f64;
            plus_dm_smooth = (plus_dm_smooth * (period - 1) as f64 + current_plus_dm) / period as f64;
            minus_dm_smooth = (minus_dm_smooth * (period - 1) as f64 + current_minus_dm) / period as f64;
            
            // Calculate DI values
            if tr_smooth > 0.0 {
                plus_di[i] = 100.0 * plus_dm_smooth / tr_smooth;
                minus_di[i] = 100.0 * minus_dm_smooth / tr_smooth;
            } else {
                plus_di[i] = 0.0;
                minus_di[i] = 0.0;
            }
        }
        
        Ok((
            PyArray1::from_array(py, &plus_di).to_owned(),
            PyArray1::from_array(py, &minus_di).to_owned()
        ))
    })
}

/// Calculate CHOP (Choppiness Index) - Ultra-optimized version
#[pyfunction]
pub fn chop(candles: PyReadonlyArray2<f64>, period: usize, scalar: f64, drift: usize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        let candles_array = candles.as_array();
        let n = candles_array.nrows();
        
        // Initialize result array
        let mut result = Array1::<f64>::from_elem(n, f64::NAN);
        
        if n < period {
            return Ok(PyArray1::from_array(py, &result).to_owned());
        }
        
        // Extract OHLCV data
        let close = candles_array.column(2);
        let high = candles_array.column(3);
        let low = candles_array.column(4);
        
        // Calculate True Range (TR) array
        let mut tr = Array1::<f64>::zeros(n);
        tr[0] = high[0] - low[0];
        for i in 1..n {
            let hl = high[i] - low[i];
            let hc = (high[i] - close[i - 1]).abs();
            let lc = (low[i] - close[i - 1]).abs();
            tr[i] = hl.max(hc).max(lc);
        }
        
        // Calculate ATR using Wilder's smoothing or simple average based on drift
        let mut atr = Array1::<f64>::from_elem(n, f64::NAN);
        
        if drift == 1 {
            // Simple case: ATR = TR
            atr.assign(&tr);
        } else {
            // Wilder's smoothing for ATR
            // Calculate initial ATR as simple average of first 'drift' values
            let mut sum = 0.0;
            for i in 0..drift {
                sum += tr[i];
            }
            atr[drift - 1] = sum / drift as f64;
            
            // Apply Wilder's smoothing for subsequent values
            let alpha = 1.0 / drift as f64;
            for i in drift..n {
                atr[i] = alpha * tr[i] + (1.0 - alpha) * atr[i - 1];
            }
        }
        
        // Pre-calculate log10(period) for efficiency
        let log_period = (period as f64).log10();
        
        // Use rolling sum algorithm for ATR sum (O(n) instead of O(n*p))
        let mut atr_sum = 0.0;
        let mut highest = f64::NEG_INFINITY;
        let mut lowest = f64::INFINITY;
        
        // Initialize the first window
        for i in 0..period {
            if !atr[i].is_nan() {
                atr_sum += atr[i];
            }
            if high[i] > highest {
                highest = high[i];
            }
            if low[i] < lowest {
                lowest = low[i];
            }
        }
        
        // Use deque-like structures for efficient rolling max/min
        use std::collections::VecDeque;
        let mut max_deque: VecDeque<(usize, f64)> = VecDeque::new();
        let mut min_deque: VecDeque<(usize, f64)> = VecDeque::new();
        
        // Initialize deques for the first window
        for i in 0..period {
            // Maintain max deque (decreasing order)
            while !max_deque.is_empty() && max_deque.back().unwrap().1 <= high[i] {
                max_deque.pop_back();
            }
            max_deque.push_back((i, high[i]));
            
            // Maintain min deque (increasing order)
            while !min_deque.is_empty() && min_deque.back().unwrap().1 >= low[i] {
                min_deque.pop_back();
            }
            min_deque.push_back((i, low[i]));
        }
        
        // Calculate first CHOP value
        if atr_sum > 0.0 {
            let range = highest - lowest;
            if range > 0.0 {
                result[period - 1] = (scalar * (atr_sum.log10() - range.log10())) / log_period;
            }
        }
        
        // Rolling window calculation for subsequent values
        for i in period..n {
            // Update rolling ATR sum
            if !atr[i].is_nan() {
                atr_sum += atr[i];
            }
            if !atr[i - period].is_nan() {
                atr_sum -= atr[i - period];
            }
            
            // Remove elements outside the window from deques
            while !max_deque.is_empty() && max_deque.front().unwrap().0 <= i - period {
                max_deque.pop_front();
            }
            while !min_deque.is_empty() && min_deque.front().unwrap().0 <= i - period {
                min_deque.pop_front();
            }
            
            // Add new element to deques
            while !max_deque.is_empty() && max_deque.back().unwrap().1 <= high[i] {
                max_deque.pop_back();
            }
            max_deque.push_back((i, high[i]));
            
            while !min_deque.is_empty() && min_deque.back().unwrap().1 >= low[i] {
                min_deque.pop_back();
            }
            min_deque.push_back((i, low[i]));
            
            // Get current max and min
            let current_highest = max_deque.front().unwrap().1;
            let current_lowest = min_deque.front().unwrap().1;
            
            // Calculate CHOP
            if atr_sum > 0.0 {
                let range = current_highest - current_lowest;
                if range > 0.0 {
                    result[i] = (scalar * (atr_sum.log10() - range.log10())) / log_period;
                }
            }
        }
        
        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}