pub mod dfg;
pub mod theory;

mod impl_dfg3egraph;
mod impl_dfg3lira;

use ahash::AHashMap;
use std::sync::LazyLock;

pub static IMPLICITNESS_STD: LazyLock<AHashMap<&'static str, dfg::Implicitness>> =
    LazyLock::new(|| {
        let mut r = AHashMap::new();
        for (ik, kinds) in [
            (
                dfg::Implicitness::Pure,
                &[
                    "input",
                    "const",
                    "dyn_const",
                    "op",
                    "broadcast",
                    "index",
                    "gather",
                    "extract_first",
                    "extend_zero",
                    "extend_ones",
                    "cvi",
                    "reinterpret",
                    "fold.op",
                    "scan.op",
                ][..],
            ),
            (
                dfg::Implicitness::Read,
                &["cond.pc.read", "cond.sys_reg.read", "read", "cond.read"],
            ),
            (
                dfg::Implicitness::Write,
                &[
                    "output",
                    "snippet",
                    "cond.pc.write",
                    "cond.sys_reg.write",
                    "fop",
                    "env",
                    "cond.env",
                    "write",
                    "cond.write",
                    "fold.fop",
                    "scan.fop",
                ],
            ),
        ] {
            for kind in kinds {
                r.insert(*kind, ik);
            }
        }
        r
    });
