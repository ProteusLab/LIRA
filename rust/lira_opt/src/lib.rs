mod ops_generalization;
mod theory;
mod transformations;
mod utils;

pub struct Arch(pub lira::Arch);
pub use theory::Lira as Theory;

use utils::get_;
