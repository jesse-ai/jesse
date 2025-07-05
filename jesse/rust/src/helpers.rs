use pyo3::prelude::*;
use numpy::{PyArray1, PyReadonlyArray1};
use ndarray::Array1;

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

/// Calculate Alligator indicator (Jaw, Teeth, Lips)
#[pyfunction]
pub fn alligator(source: PyReadonlyArray1<f64>) -> PyResult<(Py<PyArray1<f64>>, Py<PyArray1<f64>>, Py<PyArray1<f64>>)> {
    Python::with_gil(|py| {
        // Calculate the three SMMA lines first
        let jaw_smma = smma(source.clone(), 13)?;   // 13-period SMMA
        let teeth_smma = smma(source.clone(), 8)?;  // 8-period SMMA
        let lips_smma = smma(source, 5)?;           // 5-period SMMA

        // Now apply the required forward shifts
        let jaw_shifted = crate::utils::shift(jaw_smma.as_ref(py).readonly(), 8)?;   // shift by 8
        let teeth_shifted = crate::utils::shift(teeth_smma.as_ref(py).readonly(), 5)?; // shift by 5
        let lips_shifted = crate::utils::shift(lips_smma.as_ref(py).readonly(), 3)?;   // shift by 3

        Ok((jaw_shifted, teeth_shifted, lips_shifted))
    })
} 