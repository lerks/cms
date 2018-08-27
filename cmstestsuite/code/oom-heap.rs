use std::io;

fn main()
{
    let mut v = vec![0; 128 * 1024 * 1024];
    let mut s = String::new();
    match io::stdin().read_line(&mut s)
    {
        Ok(_) => v[128 * 1024 * 1024 - 1] = s.trim().parse::<i32>().unwrap(),
        Err(why) => panic!("{}", why),
    };
    println!("correct {}", v[128 * 1024 * 1024 - 1]);
}
