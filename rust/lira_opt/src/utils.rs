macro_rules! get_ {
    ($s:tt $($ident:ident)*) => {
        $( let $ident = $s.$ident; )*
    };
}
pub(crate) use get_;
