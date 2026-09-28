mod ops_generalization;
mod reg_access;
mod snippet2rewrite;
mod theory;
mod transformations;
mod utils;

pub struct Arch(pub lira::Arch);
pub use reg_access::optimize_reg_writes;
pub use theory::Lira as Theory;

use utils::get_;
